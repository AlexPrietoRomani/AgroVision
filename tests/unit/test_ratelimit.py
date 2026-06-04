"""
Archivo: test_ratelimit.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias del limitador de tasa (ventana deslizante en memoria) usado como
mitigación de abuso/DDoS de la API. Se inyecta un reloj falso para determinismo.

Ejecución:
    uv run python -m pytest tests/unit/test_ratelimit.py
"""

from __future__ import annotations

from backend.core.ratelimit import SlidingWindowRateLimiter


class _FakeClock:
    """Reloj controlable para las pruebas (segundos)."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_permite_hasta_el_maximo_y_luego_bloquea() -> None:
    """Admite `max` peticiones en la ventana y rechaza la siguiente."""
    clock = _FakeClock()
    rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=60, clock=clock)
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-1") is False  # 4ª en la misma ventana → bloqueada


def test_la_ventana_se_desliza() -> None:
    """Al avanzar el tiempo más allá de la ventana, vuelve a permitir."""
    clock = _FakeClock()
    rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=60, clock=clock)
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-1") is False
    clock.t += 61  # pasa la ventana
    assert rl.allow("ip-1") is True


def test_claves_independientes() -> None:
    """Cada clave (IP) tiene su propio cupo."""
    clock = _FakeClock()
    rl = SlidingWindowRateLimiter(max_requests=1, window_seconds=60, clock=clock)
    assert rl.allow("ip-1") is True
    assert rl.allow("ip-2") is True  # otra IP no se ve afectada
    assert rl.allow("ip-1") is False


def test_max_cero_desactiva_el_limite() -> None:
    """`max_requests<=0` desactiva el limitador (siempre permite)."""
    rl = SlidingWindowRateLimiter(max_requests=0, window_seconds=60, clock=_FakeClock())
    for _ in range(1000):
        assert rl.allow("ip-1") is True
