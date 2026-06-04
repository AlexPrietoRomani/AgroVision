"""
Archivo: ratelimit.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Limitador de tasa **en memoria** (ventana deslizante) usado por el gateway como
mitigación de abuso y picos de tráfico (defensa en profundidad junto al borde de
Hugging Face Spaces). Es por proceso: suficiente para una sola instancia (HF free).
NO sustituye una protección DDoS de red (eso lo aporta el edge del host).

Estructura Interna:
    - `SlidingWindowRateLimiter`: cuenta peticiones por clave (IP) en una ventana móvil.

Entradas / Dependencias:
    - Biblioteca estándar (`collections.deque`, `time`).

Ejemplo de Integración:
    from backend.core.ratelimit import SlidingWindowRateLimiter
    rl = SlidingWindowRateLimiter(max_requests=120, window_seconds=60)
    if not rl.allow(client_ip): ...  # responder 429
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    """
    Limita peticiones por clave en una ventana de tiempo deslizante.

    Args:
        max_requests (int): Máximo de peticiones por ventana. `<= 0` desactiva el límite.
        window_seconds (float): Tamaño de la ventana en segundos.
        clock (Callable[[], float]): Fuente de tiempo monótono (inyectable en tests).
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    @property
    def enabled(self) -> bool:
        """True si el limitador está activo (`max_requests > 0`)."""
        return self.max_requests > 0

    def allow(self, key: str) -> bool:
        """
        Registra una petición de `key` y devuelve si está permitida.

        Returns:
            bool: True si está dentro del cupo; False si excede el límite.
        """
        if not self.enabled:
            return True
        now = self._clock()
        cutoff = now - self.window
        bucket = self._hits.setdefault(key, deque())
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True
