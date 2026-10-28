"""
Archivo: schemas.py (core/dominio)
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Esquemas de dominio de la plataforma completa (Fase 1) con la selección de variables
satelitales (Fase 5). Modelan las entidades geoespaciales y analíticas con sus
invariantes: una parcela (`FieldIn`/`FieldOut`) lleva un polígono GeoJSON validado
(anillo cerrado, EPSG:4326) y una lista no vacía de índices satelitales admitidos; un
punto NDVI vive en [-1, 1]; un mensaje de chat solo admite los roles 'user' o
'assistant'. Validar aquí evita insertar geometría, índices o variables inválidas en
PostGIS.

Acciones Principales:
    - Declara los contratos de dominio compartidos por servicios, repos y API.
    - Normaliza y valida la selección de variables satelitales de cada parcela.

Estructura Interna:
    - `VALID_SATELLITE_INDICES`: catálogo de índices espectrales admitidos.
    - `FieldIn` / `FieldOut`: alta y lectura de parcelas.
    - `NDVIPoint`: observación de la serie temporal NDVI.
    - `WeatherPoint`: observación agroclimática diaria/mensual.
    - `ChatMessage`: turno de la memoria conversacional.

Entradas / Dependencias:
    - `pydantic`.

Salidas / Efectos:
    - Ninguno; expone modelos de validación/serialización.

Ejemplo de Integración:
    from backend.core.schemas import FieldIn
    parcela = FieldIn(name="Lote A", geojson={"type": "Polygon", "coordinates": [...]})
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

VALID_SATELLITE_INDICES: tuple[str, ...] = ("ndvi", "evi", "savi", "ndwi", "ndre")


def _validate_selected_indices(value: list[str]) -> list[str]:
    """
    Normaliza y valida una selección de variables satelitales.

    Convierte cada índice a minúsculas, elimina espacios y duplicados preservando el
    orden original, y rechaza listas vacías o valores fuera del catálogo.

    Args:
        value (list[str]): Índices propuestos por el usuario.

    Returns:
        list[str]: Índices normalizados y sin duplicados.

    Raises:
        ValueError: Si la lista está vacía o contiene un índice no admitido.
    """
    if not value:
        raise ValueError("Debes seleccionar al menos una variable satelital.")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Cada variable satelital debe ser una cadena de texto.")
        index = item.strip().lower()
        if index not in VALID_SATELLITE_INDICES:
            raise ValueError(
                f"Índice satelital no válido: '{item}'. "
                f"Válidos: {', '.join(VALID_SATELLITE_INDICES)}."
            )
        if index not in cleaned:
            cleaned.append(index)
    return cleaned


class FieldIn(BaseModel):
    """Datos de alta de una parcela: nombre, polígono y variables satelitales."""

    name: str = Field(min_length=1, description="Nombre legible de la parcela")
    geojson: dict = Field(description="Geometría GeoJSON tipo Polygon en EPSG:4326")
    crop_variety: str | None = Field(
        default=None, max_length=120, description="Variedad del cultivo (p. ej. Arándanos)"
    )
    selected_indices: list[str] = Field(
        default_factory=lambda: ["ndvi"],
        description="Variables satelitales a calcular (ndvi, evi, savi, ndwi, ndre)",
    )

    @field_validator("selected_indices")
    @classmethod
    def _validar_selected_indices(cls, value: list[str]) -> list[str]:
        """Valida y normaliza la selección inicial de variables satelitales."""
        return _validate_selected_indices(value)

    @field_validator("geojson")
    @classmethod
    def _validar_poligono(cls, value: dict) -> dict:
        """
        Verifica que la geometría sea un Polygon con un anillo cerrado y >=4 vértices.

        Args:
            value (dict): Geometría GeoJSON propuesta.

        Returns:
            dict: La misma geometría si es válida.

        Raises:
            ValueError: Si no es Polygon, el anillo no está cerrado o tiene <4 vértices.
        """
        if value.get("type") != "Polygon":
            raise ValueError("La geometría debe ser de tipo 'Polygon'.")
        coordinates = value.get("coordinates") or []
        if not coordinates or not coordinates[0]:
            raise ValueError("El polígono no tiene coordenadas.")
        ring = coordinates[0]
        if len(ring) < 4:
            raise ValueError("El anillo del polígono requiere al menos 4 vértices.")
        if ring[0] != ring[-1]:
            raise ValueError("El polígono debe estar cerrado (primer punto == último).")
        return value


class FieldUpdate(BaseModel):
    """Atributos actualizables opcionales de una parcela."""

    crop_variety: str | None = Field(default=None, description="Variedad del cultivo")
    field_type: str | None = Field(default=None, description="Tipo de lote/campo")
    soil_type: str | None = Field(default=None, description="Tipo de suelo")
    irrigation_system: str | None = Field(default=None, description="Sistema de riego")
    pests_diseases: str | None = Field(default=None, description="Plagas y enfermedades")
    plantation_date: dt.date | None = Field(default=None, description="Fecha de plantación")
    num_plants: int | None = Field(default=None, ge=0, description="Número de plantas")
    historical_yield: str | None = Field(default=None, description="Rendimiento histórico")
    target_market: str | None = Field(default=None, description="Mercados objetivo")
    document_metadata: str | None = Field(default=None, description="Metadatos de documentos")
    selected_indices: list[str] | None = Field(
        default=None,
        description="Variables satelitales de la parcela (None si no se actualizan)",
    )

    @field_validator("selected_indices")
    @classmethod
    def _validar_selected_indices(cls, value: list[str] | None) -> list[str] | None:
        """Valida la selección cuando se envía; `None` significa no modificarla."""
        if value is None:
            return None
        return _validate_selected_indices(value)


class FieldOut(BaseModel):
    """Representación de lectura de una parcela persistida."""

    id: str = Field(description="Identificador único (UUID) de la parcela")
    name: str = Field(description="Nombre legible de la parcela")
    area_ha: float | None = Field(default=None, ge=0, description="Área en hectáreas (PostGIS)")
    crop_variety: str | None = Field(default=None, description="Variedad del cultivo")
    field_type: str | None = Field(default=None, description="Tipo de lote/campo")
    soil_type: str | None = Field(default=None, description="Tipo de suelo")
    irrigation_system: str | None = Field(default=None, description="Sistema de riego")
    pests_diseases: str | None = Field(default=None, description="Plagas y enfermedades")
    plantation_date: dt.date | None = Field(default=None, description="Fecha de plantación")
    num_plants: int | None = Field(default=None, description="Número de plantas")
    historical_yield: str | None = Field(default=None, description="Rendimiento histórico")
    target_market: str | None = Field(default=None, description="Mercados objetivo")
    document_metadata: str | None = Field(default=None, description="Metadatos de documentos")


class NDVIPoint(BaseModel):
    """Observación de la serie temporal de NDVI (una fecha)."""

    date: dt.date = Field(description="Fecha de la escena (o primer día del mes si es mensual)")
    mean_ndvi: float = Field(ge=-1, le=1, description="NDVI medio zonal en [-1, 1]")
    min_ndvi: float | None = Field(default=None, ge=-1, le=1)
    max_ndvi: float | None = Field(default=None, ge=-1, le=1)
    cloud_cover: float | None = Field(default=None, ge=0, le=100, description="% de nubes")
    source: str = Field(default="sentinel2", description="Origen de la observación")


class IndexPoint(BaseModel):
    """Observación de la serie temporal de un índice espectral genérico."""

    date: dt.date = Field(description="Fecha de la escena (primer día del mes)")
    index_type: str = Field(description="Tipo de índice: ndvi, evi, savi, ndwi, ndre")
    mean_value: float = Field(description="Valor medio zonal del índice")
    min_value: float | None = Field(default=None)
    max_value: float | None = Field(default=None)
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    source: str = Field(default="sentinel2")


class WeatherPoint(BaseModel):
    """Observación agroclimática por fecha (todas las variables son opcionales)."""

    date: dt.date = Field(description="Fecha de la observación")
    precip_mm: float | None = Field(default=None, ge=0, description="Precipitación (mm)")
    temp_mean_c: float | None = Field(default=None, description="Temperatura media (°C)")
    radiation: float | None = Field(default=None, ge=0, description="Radiación de onda corta")


class ChatMessage(BaseModel):
    """Turno de la memoria conversacional del agente RAG."""

    role: Literal["user", "assistant"] = Field(description="Emisor del mensaje")
    content: str = Field(min_length=1, description="Texto del turno")
    session_id: str = Field(min_length=1, description="Hilo conversacional")
