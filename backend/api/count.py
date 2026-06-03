"""
Archivo: count.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Define las rutas HTTP del MVP: el healthcheck `/api/status` y el conteo síncrono
`/api/count`. El conteo respeta el modo **standby**: mientras `COUNTING_ENABLED`
sea falso o el modelo no esté cargado, responde 503 con un mensaje claro en vez
de intentar inferir.

Acciones Principales:
    - Expone `/api/status` (estado + bandera de conteo).
    - Expone `/api/count` (inferencia síncrona, gateada por standby).

Estructura Interna:
    - `router`: APIRouter con las rutas del MVP.
    - `_draw_overlay`: dibuja las cajas detectadas sobre la imagen.

Entradas / Dependencias:
    - `fastapi`, `numpy`, `opencv-python`, `backend.config`, `backend.core.*`, `backend.schemas`.

Salidas / Efectos:
    - Ninguno persistente; la respuesta es efímera (overlay en base64).

Integración UI:
    - Este router es montado por `backend.main:app`.
    - La UI Shiny consume `/api/status` y `/api/count` vía HTTPS.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from backend.config import get_settings
from backend.core.detection import CLASS_PLANT, Detection
from backend.core.metrics import compute_metrics
from backend.schemas import CountResponse, StatusResponse

router = APIRouter()

_OVERLAY_COLOR_BGR: tuple[int, int, int] = (61, 128, 21)  # verde Deep Canopy (#15803D) en BGR
_OVERLAY_THICKNESS: int = 2


def _draw_overlay(image_bgr: np.ndarray, detections: list[Detection]) -> str:
    """
    Dibuja las cajas detectadas sobre la imagen y la codifica como PNG en base64.

    Args:
        image_bgr (np.ndarray): Imagen original en formato BGR.
        detections (list[Detection]): Detecciones a superponer.

    Returns:
        str: Imagen anotada (PNG) codificada en base64.
    """
    overlay = image_bgr.copy()
    for detection in detections:
        top_left = (int(detection.x1), int(detection.y1))
        bottom_right = (int(detection.x2), int(detection.y2))
        cv2.rectangle(overlay, top_left, bottom_right, _OVERLAY_COLOR_BGR, _OVERLAY_THICKNESS)
    _, buffer = cv2.imencode(".png", overlay)
    return base64.b64encode(buffer.tobytes()).decode("ascii")


@router.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """
    Devuelve el estado del backend y si el módulo de conteo está activo.

    Returns:
        StatusResponse: Estado, nombre/versión del modelo y bandera de conteo.
    """
    settings = get_settings()
    return StatusResponse(
        status="ok",
        model="agrovision-plantcount",
        version=settings.model_version,
        counting_enabled=settings.counting_enabled,
    )


@router.post("/api/count", response_model=CountResponse)
async def post_count(
    request: Request,
    file: UploadFile = File(...),
    area_ha: float = Form(default=1.0),
) -> CountResponse:
    """
    Ejecuta el conteo síncrono sobre un ortomosaico, respetando el modo standby.

    Args:
        request (Request): Petición; expone el adaptador en `request.app.state`.
        file (UploadFile): Ortomosaico RGB en formato JPG/PNG/TIFF.
        area_ha (float): Área del lote en hectáreas para calcular densidad.

    Returns:
        CountResponse: Conteo, densidad, malezas, fallas, confianza y overlay.

    Raises:
        HTTPException: 503 si el conteo está en standby; 400 si la imagen es inválida.
    """
    settings = get_settings()
    adapter = getattr(request.app.state, "adapter", None)

    if not settings.counting_enabled or adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Módulo de conteo en standby: el modelo aún no está disponible. "
                "Se activará cuando el repo del modelo publique el artefacto."
            ),
        )

    raw_bytes = await file.read()
    image_bgr = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo decodificar la imagen. Use JPG, PNG o TIFF válido.",
        )

    detections = adapter.predict(image_bgr, confidence=settings.confidence_threshold)
    metrics = compute_metrics(detections, area_ha=area_ha)
    plant_detections = [d for d in detections if d.class_id == CLASS_PLANT]
    overlay_b64 = _draw_overlay(image_bgr, plant_detections)

    return CountResponse(
        count=metrics["count"],
        density=metrics["density"],
        weeds=metrics["weeds"],
        failures=metrics["failures"],
        confidence=metrics["confidence"],
        overlay_b64=overlay_b64,
    )
