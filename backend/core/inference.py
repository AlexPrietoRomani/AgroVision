"""
Archivo: inference.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Adaptador de inferencia **agnóstico a la arquitectura**. Carga el artefacto ONNX
del modelo de conteo con onnxruntime y delega el decode según la arquitectura
declarada (YOLO26 o RF-DETR), manteniendo la app desacoplada del modelo concreto
publicado por el repo del modelo. En el MVP el conteo está en standby, por lo que
el decode permanece como contrato pendiente hasta que el modelo se publique.

Sustentación Científica: [Opcional]
Los detectores objetivo (YOLO26, RF-DETR) son NMS-free, por lo que el conteo
equivale al número de detecciones que superan el umbral de confianza.

Acciones Principales:
    - Carga un modelo ONNX y expone `predict` para obtener detecciones.

Estructura Interna:
    - `ModelNotAvailableError`: error cuando el modelo no está disponible.
    - `InferenceAdapter`: envuelve la sesión ONNX y despacha el decode por arquitectura.
    - `load_adapter`: valida la ruta y construye el adaptador.

Entradas / Dependencias:
    - `numpy`, `onnxruntime` (import diferido), `backend.core.detection.Detection`.

Salidas / Efectos:
    - Ninguno persistente; ejecuta inferencia en memoria.

Ejemplo de Integración:
    from backend.core.inference import load_adapter
    adapter = load_adapter("models/agrovision-plantcount-v2.0.0.onnx", "yolo26n")
    detecciones = adapter.predict(imagen_bgr, confidence=0.25)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.core.detection import Detection

SUPPORTED_ARCHITECTURES: frozenset[str] = frozenset({"yolo26n", "rfdetr_nano"})


class ModelNotAvailableError(RuntimeError):
    """Se lanza cuando el modelo de conteo no está disponible (standby o archivo ausente)."""


class InferenceAdapter:
    """
    Adaptador de inferencia agnóstico a la arquitectura del modelo de conteo.

    Envuelve una sesión de onnxruntime y traduce su salida a una lista de
    `Detection`, delegando en el decode específico de cada arquitectura soportada.
    """

    def __init__(self, model_path: str, architecture: str) -> None:
        """
        Inicializa la sesión ONNX para el modelo indicado.

        Args:
            model_path (str): Ruta al artefacto `.onnx` del modelo de conteo.
            architecture (str): Arquitectura del modelo ('yolo26n' o 'rfdetr_nano').

        Raises:
            ModelNotAvailableError: Si la arquitectura no está soportada.
        """
        if architecture not in SUPPORTED_ARCHITECTURES:
            raise ModelNotAvailableError(
                f"Arquitectura no soportada: {architecture}. "
                f"Soportadas: {sorted(SUPPORTED_ARCHITECTURES)}."
            )
        import onnxruntime as ort  # import diferido: onnxruntime no se exige en modo standby

        self._architecture = architecture
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def predict(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Ejecuta la inferencia sobre una imagen y devuelve las detecciones.

        Args:
            image_bgr (np.ndarray): Imagen RGB/BGR como arreglo de NumPy.
            confidence (float): Umbral mínimo de confianza para conservar detecciones.

        Returns:
            list[Detection]: Detecciones que superan el umbral (sin NMS, modelos NMS-free).
        """
        if self._architecture == "yolo26n":
            return self._decode_yolo(image_bgr, confidence)
        return self._decode_detr(image_bgr, confidence)

    def _decode_yolo(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Decodifica la salida de un modelo YOLO26 a una lista de detecciones.

        Nota: el decode concreto se implementa cuando el repo del modelo publique el
        artefacto YOLO26 y se conozca el layout exacto del tensor de salida.

        Raises:
            NotImplementedError: Mientras el modelo de conteo esté en standby.
        """
        raise NotImplementedError(
            "Decode YOLO26 pendiente: se implementa al publicar el modelo de conteo."
        )

    def _decode_detr(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Decodifica la salida de un modelo RF-DETR a una lista de detecciones.

        Nota: el decode concreto se implementa cuando el repo del modelo publique el
        artefacto RF-DETR y se conozca el layout exacto del tensor de salida.

        Raises:
            NotImplementedError: Mientras el modelo de conteo esté en standby.
        """
        raise NotImplementedError(
            "Decode RF-DETR pendiente: se implementa al publicar el modelo de conteo."
        )


def load_adapter(model_path: str, architecture: str) -> InferenceAdapter:
    """
    Valida la existencia del artefacto y construye el adaptador de inferencia.

    Args:
        model_path (str): Ruta al artefacto `.onnx` del modelo de conteo.
        architecture (str): Arquitectura del modelo ('yolo26n' o 'rfdetr_nano').

    Returns:
        InferenceAdapter: Adaptador listo para inferir.

    Raises:
        ModelNotAvailableError: Si el archivo del modelo no existe en `model_path`.
    """
    if not Path(model_path).exists():
        raise ModelNotAvailableError(
            f"Modelo no encontrado en {model_path}. Se descarga de Hugging Face Hub "
            "en el build cuando el repo del modelo publique el artefacto."
        )
    return InferenceAdapter(model_path, architecture)
