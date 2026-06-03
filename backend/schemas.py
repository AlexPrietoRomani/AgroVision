"""
Archivo: schemas.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Define los contratos de datos (Pydantic) que entran y salen de la API del MVP.
Validan los límites del sistema, documentan el acuerdo UI↔backend y rechazan
payloads inválidos antes de que contaminen la lógica.

Acciones Principales:
    - Declara los esquemas de respuesta del healthcheck y del conteo.

Estructura Interna:
    - `StatusResponse`: respuesta del endpoint de salud.
    - `CountResponse`: respuesta del endpoint de conteo.

Entradas / Dependencias:
    - `pydantic`.

Salidas / Efectos:
    - Ninguno; expone modelos de validación/serialización.

Ejemplo de Integración:
    from backend.schemas import CountResponse
    respuesta = CountResponse(count=124, density=72400, weeds=12,
                              failures=1.2, confidence=0.91, overlay_b64="...")
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class StatusResponse(BaseModel):
    """Respuesta del healthcheck del backend, incluye el estado del módulo de conteo."""

    status: str = Field(default="ok")
    model: str = Field(description="Nombre de marca del modelo de conteo")
    version: str = Field(description="Versión semántica del modelo predeterminado")
    counting_enabled: bool = Field(description="Indica si el conteo está activo o en standby")
    model_backend: str = Field(
        default="standby", description="Backend activo: 'mock', 'onnx' o 'standby'"
    )


class CountResponse(BaseModel):
    """Resultado del conteo de plantas sobre un ortomosaico RGB."""

    count: int = Field(ge=0, description="Total de plantas/arbustos detectados")
    density: float = Field(ge=0, description="Plantas por hectárea")
    weeds: int = Field(ge=0, description="Número de malezas detectadas")
    failures: float = Field(ge=0, le=100, description="Porcentaje de fallas de siembra")
    confidence: float = Field(ge=0, le=1, description="Confianza media de las detecciones")
    overlay_b64: str = Field(description="Imagen anotada (PNG) codificada en base64")

    @field_validator("confidence")
    @classmethod
    def _validar_confianza(cls, value: float) -> float:
        """
        Verifica que la confianza media esté estrictamente en el rango [0, 1].

        Args:
            value (float): Confianza media propuesta.

        Returns:
            float: La misma confianza si es válida.

        Raises:
            ValueError: Si la confianza queda fuera del rango [0, 1].
        """
        if not 0.0 <= value <= 1.0:
            raise ValueError("La confianza debe estar en el rango [0, 1].")
        return value
