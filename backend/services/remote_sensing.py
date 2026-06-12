"""
Archivo: remote_sensing.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Teledetección NDVI sobre Sentinel-2 usando **Sentinel Hub en Copernicus Data Space
(CDSE)** con OAuth client credentials (BYOK). En vez de descargar COGs con rasterio,
se usan dos APIs HTTP del propio CDSE:
  - **Statistical API**: serie temporal NDVI agregada por mes (mean/min/max) sobre el
    polígono, con default de los últimos 5 años.
  - **Process API**: PNG colorizado (heatmap NDVI ~10 m/px) para la capa del mapa.
Es más fiable y ligero en capa gratuita que el pipeline rasterio/GDAL.

Acciones Principales:
    - Obtiene token CDSE, calcula la serie NDVI mensual y el heatmap PNG.

Estructura Interna:
    - `_get_token`: client_credentials -> access_token (cacheado por expiración).
    - `_default_range`: rango por defecto (últimos 5 años).
    - `_parse_stats`: parseo puro de la respuesta de la Statistical API a la serie.
    - `ndvi_series_monthly` / `ndvi_heatmap_png`: llamadas a SH (async).

Entradas / Dependencias:
    - `httpx`; credenciales Copernicus (client_id/secret) del usuario.

Salidas / Efectos:
    - Llamadas HTTPS a CDSE; no persiste credenciales.

Ejemplo de Integración:
    from backend.services.remote_sensing import ndvi_series_monthly
    serie = await ndvi_series_monthly(geojson, None, None, cid, secret)
"""

from __future__ import annotations

import datetime as dt
import logging
import time

import httpx
from dateutil.relativedelta import relativedelta

from backend.api.events import emit as emit_event

_logger = logging.getLogger("agrovision.remote_sensing")

_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
_CRS_4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"
_RES_DEG = 0.0001  # ~10 m/px en EPSG:4326 (grados)

# Mapa de índices a sus bandas Sentinel-2 y fórmulas.
# Cada entrada: bandas_sensor (para el input del evalscript), bands_vis (para vis),
# output_id, formula JS, rango del índice, color ramp stops, color ramp colores.
_INDEX_CONFIG: dict[str, dict] = {
    "ndvi": {
        "bands_sensor": ["B04", "B08", "SCL", "dataMask"],
        "bands_vis": ["B04", "B08", "dataMask"],
        "output_id": "ndvi",
        "formula": "(s.B08 - s.B04) / (s.B08 + s.B04)",
        "vis_formula": "(s.B08 - s.B04) / (s.B08 + s.B04)",
        "stops": [-0.2, 0.0, 0.2, 0.4, 0.6, 0.8],
        "colors": [
            [0.65, 0, 0.15],
            [0.96, 0.43, 0.26],
            [0.99, 0.68, 0.38],
            [0.85, 0.94, 0.55],
            [0.40, 0.74, 0.39],
            [0, 0.41, 0.22],
        ],
    },
    "evi": {
        "bands_sensor": ["B02", "B04", "B08", "SCL", "dataMask"],
        "bands_vis": ["B02", "B04", "B08", "dataMask"],
        "output_id": "evi",
        "formula": "2.5 * (s.B08 - s.B04) / (s.B08 + 6.0 * s.B04 - 7.5 * s.B02 + 1.0)",
        "vis_formula": "2.5 * (s.B08 - s.B04) / (s.B08 + 6.0 * s.B04 - 7.5 * s.B02 + 1.0)",
        "stops": [-0.4, 0.0, 0.2, 0.4, 0.6, 0.8],
        "colors": [
            [0.65, 0, 0.15],
            [0.96, 0.43, 0.26],
            [0.99, 0.68, 0.38],
            [0.85, 0.94, 0.55],
            [0.40, 0.74, 0.39],
            [0, 0.41, 0.22],
        ],
    },
    "savi": {
        "bands_sensor": ["B04", "B08", "SCL", "dataMask"],
        "bands_vis": ["B04", "B08", "dataMask"],
        "output_id": "savi",
        "formula": "(s.B08 - s.B04) * 1.5 / (s.B08 + s.B04 + 0.5)",
        "vis_formula": "(s.B08 - s.B04) * 1.5 / (s.B08 + s.B04 + 0.5)",
        "stops": [-0.4, -0.1, 0.1, 0.3, 0.5, 0.7],
        "colors": [
            [0.65, 0, 0.15],
            [0.96, 0.43, 0.26],
            [0.99, 0.68, 0.38],
            [0.85, 0.94, 0.55],
            [0.40, 0.74, 0.39],
            [0, 0.41, 0.22],
        ],
    },
    "ndwi": {
        "bands_sensor": ["B03", "B08", "SCL", "dataMask"],
        "bands_vis": ["B03", "B08", "dataMask"],
        "output_id": "ndwi",
        "formula": "(s.B03 - s.B08) / (s.B03 + s.B08)",
        "vis_formula": "(s.B03 - s.B08) / (s.B03 + s.B08)",
        "stops": [-0.6, -0.3, 0.0, 0.2, 0.4, 0.7],
        "colors": [
            [0.65, 0, 0.15],
            [0.96, 0.43, 0.26],
            [0.99, 0.68, 0.38],
            [0.85, 0.94, 0.55],
            [0.40, 0.74, 0.39],
            [0, 0.41, 0.22],
        ],
    },
    "ndre": {
        "bands_sensor": ["B05", "B08", "SCL", "dataMask"],
        "bands_vis": ["B05", "B08", "dataMask"],
        "output_id": "ndre",
        "formula": "(s.B08 - s.B05) / (s.B08 + s.B05)",
        "vis_formula": "(s.B08 - s.B05) / (s.B08 + s.B05)",
        "stops": [-0.2, 0.0, 0.1, 0.2, 0.3, 0.5],
        "colors": [
            [0.65, 0, 0.15],
            [0.96, 0.43, 0.26],
            [0.99, 0.68, 0.38],
            [0.85, 0.94, 0.55],
            [0.40, 0.74, 0.39],
            [0, 0.41, 0.22],
        ],
    },
}


# Evalscript genérico para la Statistical API: acepta cualquier índice.
def _stats_evalscript(index: str) -> str:
    cfg = _INDEX_CONFIG[index]
    formula = cfg["formula"]
    output_id = cfg["output_id"]
    bands_json = str(cfg["bands_sensor"])
    return f"""//VERSION=3
function setup() {{
  return {{
    input: [{{bands: {bands_json}}}],
    output: [{{id: "{output_id}", bands: 1}}, {{id: "dataMask", bands: 1}}]
  }};
}}
function evaluatePixel(s) {{
  let val = {formula};
  let cloudy = [3, 8, 9, 10, 11].indexOf(s.SCL) > -1;
  return {{{output_id}: [val], dataMask: [cloudy ? 0 : s.dataMask]}};
}}"""


# Evalscript genérico para la Process API: coloriza cualquier índice.
def _vis_evalscript(index: str) -> str:
    cfg = _INDEX_CONFIG[index]
    formula = cfg["vis_formula"]
    stops = str(cfg["stops"])
    colors = str(cfg["colors"])
    bands_str = str(cfg["bands_vis"])
    return f"""//VERSION=3
function setup() {{
  return {{input: {bands_str}, output: {{bands: 4}}}};
}}
const STOPS = {stops};
const COLORS = {colors};
function evaluatePixel(s) {{
  let val = {formula};
  let c = colorBlend(val, STOPS, COLORS);
  return [c[0], c[1], c[2], s.dataMask];
}}"""


# Evalscripts concretos NDVI (mantenidos para compatibilidad con el router legacy).
_STATS_EVALSCRIPT = _stats_evalscript("ndvi")
_VIS_EVALSCRIPT = _vis_evalscript("ndvi")

_token_cache: dict[str, tuple[str, float]] = {}


async def _get_token(client_id: str, client_secret: str) -> str:
    """
    Obtiene un access_token de CDSE (client_credentials), cacheado hasta su expiración.

    Args:
        client_id (str): Client id del OAuth client de Copernicus.
        client_secret (str): Client secret correspondiente.

    Returns:
        str: Bearer token válido para las APIs de Sentinel Hub en CDSE.
    """
    cached = _token_cache.get(client_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()
    token = payload["access_token"]
    _token_cache[client_id] = (token, time.time() + float(payload.get("expires_in", 600)))
    return token


def _default_range() -> tuple[str, str]:
    """Devuelve el rango por defecto (últimos 5 años) como ISO datetimes UTC."""
    end = dt.date.today()
    start = end - relativedelta(years=5)
    return f"{start.isoformat()}T00:00:00Z", f"{end.isoformat()}T23:59:59Z"


def _parse_stats(payload: dict, output_id: str = "ndvi", index: str = "ndvi") -> list[dict]:
    """
    Convierte la respuesta de la Statistical API en la serie mensual de un índice.

    Args:
        payload (dict): JSON devuelto por la Statistical API.
        output_id (str): Nombre del output en el evalscript (ej. 'ndvi', 'evi').
        index (str): Nombre del índice para la clave en el dict.

    Returns:
        list[dict]: Puntos {date, mean_<index>, min_<index>, max_<index>, cloud_cover, source}
        ordenados por fecha; se omiten intervalos sin píxeles válidos.
    """
    series: list[dict] = []
    key_mean = f"mean_{index}"
    key_min = f"min_{index}"
    key_max = f"max_{index}"
    for item in payload.get("data", []):
        outputs = item.get("outputs", {})
        bands = outputs.get(output_id, {}).get("bands", {})
        stats = bands.get("B0", {}).get("stats", {})
        mean = stats.get("mean")
        if mean is None or stats.get("sampleCount", 0) == 0:
            continue
        if isinstance(mean, str):
            continue
        month = item["interval"]["from"][:7]
        series.append(
            {
                "date": f"{month}-01",
                key_mean: round(float(mean), 4),
                key_min: round(float(stats.get("min", mean)), 4),
                key_max: round(float(stats.get("max", mean)), 4),
                "cloud_cover": None,
                "source": "sentinel2",
            }
        )
    return sorted(series, key=lambda p: p["date"])


def _stats_body(geojson: dict, start: str, end: str, index: str = "ndvi") -> dict:
    """Construye el cuerpo de la Statistical API para un índice dado."""
    return {
        "input": {
            "bounds": {"geometry": geojson, "properties": {"crs": _CRS_4326}},
            "data": [{"type": "sentinel-2-l2a"}],
        },
        "aggregation": {
            "timeRange": {"from": start, "to": end},
            "aggregationInterval": {"of": "P1M"},
            "evalscript": _stats_evalscript(index),
            "resx": _RES_DEG,
            "resy": _RES_DEG,
        },
    }


async def index_series_monthly(
    geojson: dict,
    start: str | None,
    end: str | None,
    client_id: str,
    client_secret: str,
    index: str = "ndvi",
) -> list[dict]:
    """
    Calcula la serie mensual de un índice espectral (default: últimos 5 años).

    Args:
        geojson (dict): Geometría Polygon (EPSG:4326).
        start (str | None): Inicio ISO; si es None, se usan los últimos 5 años.
        end (str | None): Fin ISO; si es None, hoy.
        client_id (str): Client id de Copernicus.
        client_secret (str): Client secret de Copernicus.
        index (str): Nombre del índice ('ndvi', 'evi', 'savi', 'ndwi', 'ndre').

    Returns:
        list[dict]: Serie mensual del índice lista para persistir/graficar.
    """
    cfg = _INDEX_CONFIG[index]
    if not start or not end:
        start, end = _default_range()
    emit_event("copernicus_stats", {"index": index, "start": start[:10], "end": end[:10]})
    _logger.info("Consultando Statistical API para %s (%s a %s)", index, start[:10], end[:10])
    token = await _get_token(client_id, client_secret)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _STATS_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=_stats_body(geojson, start, end, index),
            timeout=120,
        )
    response.raise_for_status()
    data = _parse_stats(response.json(), cfg["output_id"], index)
    _logger.info("Statistical API para %s: %d puntos obtenidos", index, len(data))
    return data


async def ndvi_series_monthly(
    geojson: dict,
    start: str | None,
    end: str | None,
    client_id: str,
    client_secret: str,
) -> list[dict]:
    """Wrapper para compatibilidad: serie NDVI mensual."""
    return await index_series_monthly(geojson, start, end, client_id, client_secret, index="ndvi")


async def index_heatmap_png(
    geojson: dict,
    client_id: str,
    client_secret: str,
    start: str | None = None,
    end: str | None = None,
    size: int = 512,
    index: str = "ndvi",
) -> bytes:
    """
    Genera un PNG colorizado del índice (heatmap ~10 m/px) recortado al polígono.

    Args:
        geojson (dict): Geometría Polygon (EPSG:4326).
        client_id (str): Client id de Copernicus.
        client_secret (str): Client secret de Copernicus.
        start (str | None): Inicio del rango; default últimos 5 años.
        end (str | None): Fin del rango; default hoy.
        size (int): Lado del PNG en píxeles.
        index (str): Nombre del índice ('ndvi', 'evi', 'savi', 'ndwi', 'ndre').

    Returns:
        bytes: Imagen PNG (RGBA) del heatmap del índice.
    """
    if not start or not end:
        start, end = _default_range()
    emit_event("copernicus_process", {"index": index, "start": start[:10], "end": end[:10]})
    _logger.info("Consultando Process API para %s (heatmap)", index)
    token = await _get_token(client_id, client_secret)
    body = {
        "input": {
            "bounds": {"geometry": geojson, "properties": {"crs": _CRS_4326}},
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": start, "to": end},
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "output": {
            "width": size,
            "height": size,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": _vis_evalscript(index),
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _PROCESS_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=120,
        )
    response.raise_for_status()
    return response.content


async def ndvi_heatmap_png(
    geojson: dict,
    client_id: str,
    client_secret: str,
    start: str | None = None,
    end: str | None = None,
    size: int = 512,
) -> bytes:
    """Wrapper para compatibilidad: heatmap NDVI."""
    return await index_heatmap_png(
        geojson, client_id, client_secret, start, end, size, index="ndvi"
    )
