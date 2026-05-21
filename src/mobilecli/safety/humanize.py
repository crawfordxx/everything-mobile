"""Humanization primitives -- timing, jitter, bezier swipe.

Sourced from docs/anti-risk-control.md (timing variance > magnitude;
60%-inner-box tap jitter; bezier swipe with lateral wobble).
"""

from __future__ import annotations

import math
import random


def human_delay_s(mu: float = 1.2, sigma: float = 0.4, lo: float = 0.3, hi: float = 8.0) -> float:
    """Sample a log-normal inter-action delay in seconds. Clamped to [lo, hi]."""
    sample = random.lognormvariate(math.log(mu), sigma)
    return max(lo, min(hi, sample))


def log_normal_duration_ms(mu_ms: float = 90.0, sigma: float = 0.5) -> int:
    """Touch duration in ms. Default median 90ms."""
    return int(max(10, random.lognormvariate(math.log(mu_ms), sigma)))


def jittered_tap_point(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    """Sample a tap point within the inner 60% box of `bounds=(x1,y1,x2,y2)`."""
    x1, y1, x2, y2 = bounds
    w, h = x2 - x1, y2 - y1
    inner_x1 = x1 + int(w * 0.2)
    inner_x2 = x2 - int(w * 0.2)
    inner_y1 = y1 + int(h * 0.2)
    inner_y2 = y2 - int(h * 0.2)
    return (random.randint(inner_x1, inner_x2), random.randint(inner_y1, inner_y2))


def jittered_xy(x: int, y: int, radius: int = 8) -> tuple[int, int]:
    """Jitter a point by ±radius pixels."""
    return (x + random.randint(-radius, radius), y + random.randint(-radius, radius))


def _bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1 - t
    x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
    y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
    return (x, y)


def _ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def bezier_swipe_points(
    start: tuple[int, int],
    end: tuple[int, int],
    n_points: int = 35,
    wobble_px: int = 10,
) -> list[tuple[int, int]]:
    """Cubic-bezier swipe points with ease-in-out + lateral wobble."""
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length = max(1.0, math.hypot(dx, dy))
    nx, ny = -dy / length, dx / length
    c1 = (
        sx + dx * 0.25 + nx * random.uniform(-wobble_px, wobble_px),
        sy + dy * 0.25 + ny * random.uniform(-wobble_px, wobble_px),
    )
    c2 = (
        sx + dx * 0.75 + nx * random.uniform(-wobble_px, wobble_px),
        sy + dy * 0.75 + ny * random.uniform(-wobble_px, wobble_px),
    )
    pts: list[tuple[int, int]] = []
    for i in range(n_points):
        t = _ease_in_out(i / (n_points - 1))
        x, y = _bezier((sx, sy), c1, c2, (ex, ey), t)
        x += random.uniform(-wobble_px * 0.4, wobble_px * 0.4)
        y += random.uniform(-wobble_px * 0.4, wobble_px * 0.4)
        pts.append((int(x), int(y)))
    pts[0] = (sx, sy)
    return pts


def read_pause_s(*, text_length: int = 200, seen_recently: bool = False) -> float:
    """Sample a read-time pause for a newly loaded screen."""
    if seen_recently:
        return random.uniform(0.3, 1.2)
    base = 1.5 + min(3.0, text_length / 200.0)
    return min(5.0, base + random.uniform(0.0, 0.5))


def per_char_type_delay_s() -> float:
    """Per-character delay for ASCII typing (log-normal 120ms, σ=0.6)."""
    return random.lognormvariate(math.log(0.120), 0.6)
