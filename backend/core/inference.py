"""
Archivo: inference.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Adaptadores de inferencia del MVP, **agnósticos a la arquitectura**. Define una
interfaz común y dos implementaciones: `OnnxInferenceAdapter` (carga el artefacto
ONNX real con onnxruntime y delega el decode por arquitectura) y
`MockInferenceAdapter` (genera detecciones **falsas** plausibles para probar el
flujo completo sin el modelo real). La fábrica `create_adapter` selecciona la
implementación según el backend configurado (`mock` | `onnx`).

Sustentación Científica: [Opcional]
Los detectores objetivo (YOLO26, RF-DETR) son NMS-free, por lo que el conteo
equivale al número de detecciones que superan el umbral de confianza.

Acciones Principales:
    - Provee adaptadores de inferencia (real y mock) y su fábrica.

Estructura Interna:
    - `ModelNotAvailableError`: error cuando el modelo real no está disponible.
    - `InferenceAdapter`: protocolo común (`predict`).
    - `MockInferenceAdapter`: detecciones falsas deterministas por imagen.
    - `OnnxInferenceAdapter`: inferencia ONNX real (decode pendiente de publicación).
    - `create_adapter`: fábrica que devuelve el adaptador según el backend.

Entradas / Dependencias:
    - `numpy`, `onnxruntime` (import diferido), `backend.core.detection.Detection`.

Salidas / Efectos:
    - Ninguno persistente; ejecuta inferencia en memoria.

Ejemplo de Integración:
    from backend.core.inference import create_adapter
    adapter = create_adapter("mock", model_path="", architecture="yolo26n")
    detecciones = adapter.predict(imagen_bgr, confidence=0.25)
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol

import numpy as np

from backend.core.detection import CLASS_PLANT, CLASS_WEED, Detection

SUPPORTED_ARCHITECTURES: frozenset[str] = frozenset({"yolo26n", "rfdetr_nano"})

_MOCK_MIN_PLANTS: int = 40
_MOCK_MAX_PLANTS: int = 130
_MOCK_BOX_SIZE_PX: int = 18
_MOCK_WEED_RATIO: float = 0.08  # malezas como fracción aproximada de las plantas


class ModelNotAvailableError(RuntimeError):
    """Se lanza cuando el modelo real no está disponible (backend desconocido o archivo ausente)."""


class InferenceAdapter(Protocol):
    """Interfaz común de los adaptadores de inferencia (real y mock)."""

    def predict(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """Devuelve las detecciones de la imagen que superan el umbral de confianza."""
        ...


class MockInferenceAdapter:
    """
    Adaptador de inferencia **simulado** para validar el flujo sin el modelo real.

    Genera detecciones falsas pero plausibles (plantas y algunas malezas) dentro de
    las dimensiones de la imagen. Es **determinista por imagen** (la semilla deriva
    del contenido), respetando la convención de inferencia idempotente.
    """

    def predict(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Genera detecciones falsas plausibles para la imagen dada.

        Args:
            image_bgr (np.ndarray): Imagen RGB/BGR como arreglo de NumPy.
            confidence (float): Umbral de confianza; las cajas falsas lo superan.

        Returns:
            list[Detection]: Plantas y malezas simuladas dentro de la imagen.
        """
        height, width = image_bgr.shape[:2]
        seed = int(image_bgr.sum()) % (2**32)  # determinista: misma imagen → mismo conteo
        rng = random.Random(seed)

        plant_count = rng.randint(_MOCK_MIN_PLANTS, _MOCK_MAX_PLANTS)
        weed_count = rng.randint(0, max(1, int(plant_count * _MOCK_WEED_RATIO)))

        detections: list[Detection] = []
        for class_id, total in ((CLASS_PLANT, plant_count), (CLASS_WEED, weed_count)):
            for _ in range(total):
                detections.append(self._random_detection(rng, width, height, confidence, class_id))
        return detections

    @staticmethod
    def _random_detection(
        rng: random.Random, width: int, height: int, confidence: float, class_id: int
    ) -> Detection:
        """
        Construye una detección falsa dentro de los límites de la imagen.

        Args:
            rng (random.Random): Generador semillado por imagen.
            width (int): Ancho de la imagen en píxeles.
            height (int): Alto de la imagen en píxeles.
            confidence (float): Umbral mínimo; la confianza simulada lo supera.
            class_id (int): Clase de la detección (planta o maleza).

        Returns:
            Detection: Detección falsa con caja, confianza y clase.
        """
        max_x = max(_MOCK_BOX_SIZE_PX + 1, width - _MOCK_BOX_SIZE_PX)
        max_y = max(_MOCK_BOX_SIZE_PX + 1, height - _MOCK_BOX_SIZE_PX)
        center_x = rng.randint(_MOCK_BOX_SIZE_PX, max_x)
        center_y = rng.randint(_MOCK_BOX_SIZE_PX, max_y)
        half = _MOCK_BOX_SIZE_PX / 2
        conf = round(rng.uniform(confidence, 1.0), 3)
        return Detection(
            x1=center_x - half,
            y1=center_y - half,
            x2=center_x + half,
            y2=center_y + half,
            confidence=conf,
            class_id=class_id,
        )


class OnnxInferenceAdapter:
    """
    Adaptador de inferencia ONNX real, agnóstico a la arquitectura.

    Envuelve una sesión de onnxruntime y traduce su salida a `Detection`, delegando
    en el decode específico de cada arquitectura soportada.
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
        import onnxruntime as ort  # import diferido: onnxruntime no se exige en mock/standby

        self._architecture = architecture
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def predict(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Ejecuta la inferencia real y devuelve las detecciones.

        Args:
            image_bgr (np.ndarray): Imagen RGB/BGR como arreglo de NumPy.
            confidence (float): Umbral mínimo de confianza.

        Returns:
            list[Detection]: Detecciones que superan el umbral (modelos NMS-free).
        """
        if self._architecture == "yolo26n":
            return self._decode_yolo(image_bgr, confidence)
        return self._decode_detr(image_bgr, confidence)

    def _decode_yolo(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Decodifica la salida de un modelo YOLO26 a detecciones.

        Raises:
            NotImplementedError: Mientras el modelo de conteo no esté publicado.
        """
        raise NotImplementedError(
            "Decode YOLO26 pendiente: se implementa al publicar el modelo de conteo."
        )

    def _decode_detr(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Decodifica la salida de un modelo RF-DETR a detecciones.

        Raises:
            NotImplementedError: Mientras el modelo de conteo no esté publicado.
        """
        raise NotImplementedError(
            "Decode RF-DETR pendiente: se implementa al publicar el modelo de conteo."
        )


def create_adapter(backend: str, model_path: str, architecture: str) -> InferenceAdapter:
    """
    Fábrica que devuelve el adaptador de inferencia según el backend configurado.

    Args:
        backend (str): 'mock' (datos falsos) u 'onnx' (modelo real).
        model_path (str): Ruta al artefacto `.onnx` (solo para backend 'onnx').
        architecture (str): Arquitectura del modelo ('yolo26n' o 'rfdetr_nano').

    Returns:
        InferenceAdapter: Adaptador listo para inferir.

    Raises:
        ModelNotAvailableError: Si el backend es desconocido o el modelo real no existe.
    """
    if backend == "mock":
        return MockInferenceAdapter()
    if backend == "onnx":
        if not Path(model_path).exists():
            raise ModelNotAvailableError(
                f"Modelo no encontrado en {model_path}. Se descarga de Hugging Face Hub "
                "en el build cuando el repo del modelo publique el artefacto."
            )
        return OnnxInferenceAdapter(model_path, architecture)
    raise ModelNotAvailableError(f"Backend de modelo desconocido: {backend}. Use 'mock' u 'onnx'.")
