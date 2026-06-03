"""
Archivo: inference.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Adaptadores de inferencia del MVP, **agnósticos a la arquitectura**. Define una
interfaz común y dos implementaciones: `OnnxInferenceAdapter` (carga el artefacto
ONNX real con onnxruntime y delega el decode por arquitectura) y
`MockInferenceAdapter` (genera detecciones de prueba para validar el flujo sin el
modelo real). La fábrica `create_adapter` selecciona la implementación según el
backend configurado (`mock` | `onnx`).

Sustentación Científica: [Opcional]
Los detectores objetivo (YOLO26, RF-DETR) son NMS-free, por lo que el conteo
equivale al número de detecciones que superan el umbral de confianza.

Acciones Principales:
    - Provee adaptadores de inferencia (real y mock) y su fábrica.

Estructura Interna:
    - `ModelNotAvailableError`: error cuando el modelo real no está disponible.
    - `InferenceAdapter`: protocolo común (`predict`).
    - `MockInferenceAdapter`: detecta arbustos por color (blobs) o genera cajas aleatorias.
    - `OnnxInferenceAdapter`: inferencia ONNX real (decode pendiente de publicación).
    - `create_adapter`: fábrica que devuelve el adaptador según el backend.

Entradas / Dependencias:
    - `cv2`, `numpy`, `onnxruntime` (import diferido), `backend.core.detection.Detection`.

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

import cv2
import numpy as np

from backend.core.detection import CLASS_PLANT, CLASS_WEED, Detection

SUPPORTED_ARCHITECTURES: frozenset[str] = frozenset({"yolo26n", "rfdetr_nano"})

# Parámetros del fallback aleatorio (imágenes sin arbustos verdes reconocibles)
_MOCK_MIN_PLANTS: int = 40
_MOCK_MAX_PLANTS: int = 130
_MOCK_BOX_SIZE_PX: int = 18
_MOCK_WEED_RATIO: float = 0.08  # malezas como fracción aproximada de las plantas

# Parámetros de la detección por color (para el ortomosaico de arándano simulado)
_MOCK_MIN_DETECTED_BLOBS: int = 8  # mínimo de arbustos para usar el modo "blobs"
_BLOB_MIN_AREA_PX: int = 30  # área mínima de un blob válido
# Rangos HSV (OpenCV: H en [0,179]). Verde = arbusto; amarillo = maleza.
_GREEN_HSV_LOWER: np.ndarray = np.array([35, 40, 40], dtype=np.uint8)
_GREEN_HSV_UPPER: np.ndarray = np.array([85, 255, 255], dtype=np.uint8)
_YELLOW_HSV_LOWER: np.ndarray = np.array([20, 60, 60], dtype=np.uint8)
_YELLOW_HSV_UPPER: np.ndarray = np.array([34, 255, 255], dtype=np.uint8)


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

    Si la imagen contiene suficientes arbustos verdes reconocibles (p. ej. el
    ortomosaico de arándano simulado), los detecta por color (blobs) para que las
    cajas caigan sobre los arbustos. En cualquier otra imagen recurre a cajas
    aleatorias plausibles. Es **determinista por imagen** (la semilla deriva del
    contenido), respetando la convención de inferencia idempotente.
    """

    def predict(self, image_bgr: np.ndarray, confidence: float) -> list[Detection]:
        """
        Genera detecciones de prueba: por color si hay arbustos, o aleatorias si no.

        Args:
            image_bgr (np.ndarray): Imagen BGR como arreglo de NumPy.
            confidence (float): Umbral de confianza; las cajas simuladas lo superan.

        Returns:
            list[Detection]: Detecciones simuladas (plantas y malezas).
        """
        seed = int(image_bgr.sum()) % (2**32)  # determinista: misma imagen → mismo conteo
        rng = random.Random(seed)

        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        plants = self._detect_blobs(
            hsv, _GREEN_HSV_LOWER, _GREEN_HSV_UPPER, CLASS_PLANT, confidence, rng
        )
        if len(plants) >= _MOCK_MIN_DETECTED_BLOBS:
            weeds = self._detect_blobs(
                hsv, _YELLOW_HSV_LOWER, _YELLOW_HSV_UPPER, CLASS_WEED, confidence, rng
            )
            return plants + weeds
        return self._random_detections(image_bgr, confidence, rng)

    @staticmethod
    def _detect_blobs(
        hsv: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        class_id: int,
        confidence: float,
        rng: random.Random,
    ) -> list[Detection]:
        """
        Detecta blobs de un rango de color como cajas (clásico, sin modelo entrenado).

        Args:
            hsv (np.ndarray): Imagen en espacio HSV.
            lower (np.ndarray): Cota inferior del rango HSV.
            upper (np.ndarray): Cota superior del rango HSV.
            class_id (int): Clase asignada a los blobs encontrados.
            confidence (float): Umbral mínimo de confianza simulada.
            rng (random.Random): Generador semillado para confianzas reproducibles.

        Returns:
            list[Detection]: Una detección por blob que supere el área mínima.
        """
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: list[Detection] = []
        for contour in contours:
            if cv2.contourArea(contour) < _BLOB_MIN_AREA_PX:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            detections.append(
                Detection(
                    x1=float(x),
                    y1=float(y),
                    x2=float(x + width),
                    y2=float(y + height),
                    confidence=round(rng.uniform(confidence, 1.0), 3),
                    class_id=class_id,
                )
            )
        return detections

    def _random_detections(
        self, image_bgr: np.ndarray, confidence: float, rng: random.Random
    ) -> list[Detection]:
        """
        Genera cajas aleatorias plausibles (fallback para imágenes sin arbustos).

        Args:
            image_bgr (np.ndarray): Imagen BGR (se usan sus dimensiones).
            confidence (float): Umbral mínimo de confianza simulada.
            rng (random.Random): Generador semillado por imagen.

        Returns:
            list[Detection]: Plantas y malezas en posiciones aleatorias.
        """
        height, width = image_bgr.shape[:2]
        plant_count = rng.randint(_MOCK_MIN_PLANTS, _MOCK_MAX_PLANTS)
        weed_count = rng.randint(0, max(1, int(plant_count * _MOCK_WEED_RATIO)))

        detections: list[Detection] = []
        for class_id, total in ((CLASS_PLANT, plant_count), (CLASS_WEED, weed_count)):
            for _ in range(total):
                detections.append(self._random_box(rng, width, height, confidence, class_id))
        return detections

    @staticmethod
    def _random_box(
        rng: random.Random, width: int, height: int, confidence: float, class_id: int
    ) -> Detection:
        """
        Construye una caja aleatoria dentro de los límites de la imagen.

        Args:
            rng (random.Random): Generador semillado por imagen.
            width (int): Ancho de la imagen en píxeles.
            height (int): Alto de la imagen en píxeles.
            confidence (float): Umbral mínimo de confianza simulada.
            class_id (int): Clase de la detección (planta o maleza).

        Returns:
            Detection: Detección aleatoria con caja, confianza y clase.
        """
        max_x = max(_MOCK_BOX_SIZE_PX + 1, width - _MOCK_BOX_SIZE_PX)
        max_y = max(_MOCK_BOX_SIZE_PX + 1, height - _MOCK_BOX_SIZE_PX)
        center_x = rng.randint(_MOCK_BOX_SIZE_PX, max_x)
        center_y = rng.randint(_MOCK_BOX_SIZE_PX, max_y)
        half = _MOCK_BOX_SIZE_PX / 2
        return Detection(
            x1=center_x - half,
            y1=center_y - half,
            x2=center_x + half,
            y2=center_y + half,
            confidence=round(rng.uniform(confidence, 1.0), 3),
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
            image_bgr (np.ndarray): Imagen BGR como arreglo de NumPy.
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
        backend (str): 'mock' (datos de prueba) u 'onnx' (modelo real).
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
