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
import time

import httpx
from dateutil.relativedelta import relativedelta

_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
_CRS_4326 = "http://www.opengis.net/def/crs/EPSG/0/4326"
_RES_DEG = 0.0001  # ~10 m/px en EPSG:4326 (grados)

# Evalscript para la Statistical API: NDVI con máscara de nubes vía SCL.
_STATS_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL", "dataMask"]}],
    output: [{id: "ndvi", bands: 1}, {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  let cloudy = [3, 8, 9, 10, 11].indexOf(s.SCL) > -1;  // sombra/nube/cirros/nieve
  return {ndvi: [ndvi], dataMask: [cloudy ? 0 : s.dataMask]};
}"""

# Evalscript para la Process API: NDVI colorizado (rojo->verde) como RGBA.
_VIS_EVALSCRIPT = """//VERSION=3
function setup() {
  return {input: ["B04", "B08", "dataMask"], output: {bands: 4}};
}
const STOPS = [-0.2, 0.0, 0.2, 0.4, 0.6, 0.8];
const COLORS = [[0.65,0,0.15],[0.96,0.43,0.26],[0.99,0.68,0.38],
                [0.85,0.94,0.55],[0.40,0.74,0.39],[0,0.41,0.22]];
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  let c = colorBlend(ndvi, STOPS, COLORS);
  return [c[0], c[1], c[2], s.dataMask];
}"""

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


def _parse_stats(payload: dict) -> list[dict]:
    """
    Convierte la respuesta de la Statistical API en la serie NDVI mensual.

    Args:
        payload (dict): JSON devuelto por la Statistical API.

    Returns:
        list[dict]: Puntos {date, mean_ndvi, min_ndvi, max_ndvi, cloud_cover, source}
        ordenados por fecha; se omiten intervalos sin píxeles válidos.
    """
    series: list[dict] = []
    for item in payload.get("data", []):
        outputs = item.get("outputs", {})
        bands = outputs.get("ndvi", {}).get("bands", {})
        stats = bands.get("B0", {}).get("stats", {})
        mean = stats.get("mean")
        if mean is None or stats.get("sampleCount", 0) == 0:
            continue
        # En meses totalmente nublados/sin escena, mean puede venir como 'NaN'.
        if isinstance(mean, str):
            continue
        month = item["interval"]["from"][:7]
        series.append(
            {
                "date": f"{month}-01",
                "mean_ndvi": round(float(mean), 4),
                "min_ndvi": round(float(stats.get("min", mean)), 4),
                "max_ndvi": round(float(stats.get("max", mean)), 4),
                "cloud_cover": None,
                "source": "sentinel2",
            }
        )
    return sorted(series, key=lambda p: p["date"])


def _stats_body(geojson: dict, start: str, end: str) -> dict:
    """Construye el cuerpo de la Statistical API para NDVI mensual."""
    return {
        "input": {
            "bounds": {"geometry": geojson, "properties": {"crs": _CRS_4326}},
            "data": [{"type": "sentinel-2-l2a"}],
        },
        "aggregation": {
            "timeRange": {"from": start, "to": end},
            "aggregationInterval": {"of": "P1M"},
            "evalscript": _STATS_EVALSCRIPT,
            "resx": _RES_DEG,
            "resy": _RES_DEG,
        },
    }


async def ndvi_series_monthly(
    geojson: dict,
    start: str | None,
    end: str | None,
    client_id: str,
    client_secret: str,
) -> list[dict]:
    """
    Calcula la serie NDVI mensual de un polígono (default: últimos 5 años).

    Args:
        geojson (dict): Geometría Polygon (EPSG:4326).
        start (str | None): Inicio ISO; si es None, se usan los últimos 5 años.
        end (str | None): Fin ISO; si es None, hoy.
        client_id (str): Client id de Copernicus.
        client_secret (str): Client secret de Copernicus.

    Returns:
        list[dict]: Serie NDVI mensual lista para persistir/graficar.
    """
    if not start or not end:
        start, end = _default_range()
    token = await _get_token(client_id, client_secret)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _STATS_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=_stats_body(geojson, start, end),
            timeout=120,
        )
    response.raise_for_status()
    return _parse_stats(response.json())


async def ndvi_heatmap_png(
    geojson: dict,
    client_id: str,
    client_secret: str,
    start: str | None = None,
    end: str | None = None,
    size: int = 512,
) -> bytes:
    """
    Genera un PNG colorizado del NDVI (heatmap ~10 m/px) recortado al polígono.

    Args:
        geojson (dict): Geometría Polygon (EPSG:4326).
        client_id (str): Client id de Copernicus.
        client_secret (str): Client secret de Copernicus.
        start (str | None): Inicio del rango; default últimos 5 años.
        end (str | None): Fin del rango; default hoy.
        size (int): Lado del PNG en píxeles.

    Returns:
        bytes: Imagen PNG (RGBA) del heatmap NDVI.
    """
    if not start or not end:
        start, end = _default_range()
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
        "evalscript": _VIS_EVALSCRIPT,
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
