"""Humanlike motion + timing primitives for the CDP dispatcher.

Bezier mouse curves and Gaussian-sampled inter-event delays. Used by
the dispatcher to make agent clicks indistinguishable from a human at
the network and event level (and at the bot-detection-fingerprint level
to the extent that's testable from CDP).

All functions deterministic when given a numpy.random.Generator with a
fixed seed, so tests can pin behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np


@dataclass(frozen=True, slots=True)
class MotionPoint:
    x: float
    y: float
    delay_ms: float  # delay before this point (after the previous one)


def bezier_path(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    n_points: int = 30,
    curvature: float = 0.10,
    rng: Optional[np.random.Generator] = None,
) -> list[MotionPoint]:
    """Cubic Bezier curve from (x0,y0) to (x1,y1) with two control
    points offset perpendicular to the path by ~curvature * length.

    Returns n_points sample points with humanlike inter-point delays
    (Gaussian, 15ms mean, 5ms std, clamped to [5, 50]).

    Tested deterministic with np.random.default_rng(42).
    """
    if rng is None:
        rng = np.random.default_rng()

    dx = x1 - x0
    dy = y1 - y0
    length = max(1.0, np.hypot(dx, dy))

    # Perpendicular unit vector
    perp_x = -dy / length
    perp_y = dx / length

    # Random sign so curves arc both ways across runs
    sign = 1.0 if rng.random() < 0.5 else -1.0
    offset_mag = curvature * length

    # Two control points biased toward 1/3 and 2/3 along the path
    cx1 = x0 + dx * 0.33 + sign * perp_x * offset_mag * float(rng.uniform(0.7, 1.3))
    cy1 = y0 + dy * 0.33 + sign * perp_y * offset_mag * float(rng.uniform(0.7, 1.3))
    cx2 = x0 + dx * 0.66 + sign * perp_x * offset_mag * float(rng.uniform(0.7, 1.3))
    cy2 = y0 + dy * 0.66 + sign * perp_y * offset_mag * float(rng.uniform(0.7, 1.3))

    out: list[MotionPoint] = []
    for i in range(n_points + 1):
        t = i / n_points
        u = 1.0 - t
        bx = u**3 * x0 + 3 * u**2 * t * cx1 + 3 * u * t**2 * cx2 + t**3 * x1
        by = u**3 * y0 + 3 * u**2 * t * cy1 + 3 * u * t**2 * cy2 + t**3 * y1
        # Small jitter for naturalism
        bx += float(rng.normal(0, 0.5))
        by += float(rng.normal(0, 0.5))
        delay = float(np.clip(rng.normal(15.0, 5.0), 5.0, 50.0))
        out.append(MotionPoint(x=bx, y=by, delay_ms=delay))

    return out


def gaussian_delay(
    mean_ms: float,
    std_ms: float,
    clamp_min_ms: float,
    clamp_max_ms: float,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """Sample one inter-event delay with Gaussian distribution + clamp."""
    if rng is None:
        rng = np.random.default_rng()
    return float(np.clip(rng.normal(mean_ms, std_ms), clamp_min_ms, clamp_max_ms))


def typing_inter_char_delays(
    text: str,
    mean_ms: float = 90.0,
    std_ms: float = 40.0,
    clamp_min_ms: float = 30.0,
    clamp_max_ms: float = 250.0,
    pause_chance: float = 0.04,
    pause_mean_ms: float = 600.0,
    pause_std_ms: float = 200.0,
    rng: Optional[np.random.Generator] = None,
) -> list[float]:
    """Sample one delay per character with occasional thinking pauses
    every 8 to 15 chars on average. Returns a list of len(text) floats.
    """
    if rng is None:
        rng = np.random.default_rng()
    delays: list[float] = []
    for i, _ in enumerate(text):
        if i > 4 and rng.random() < pause_chance:
            d = float(np.clip(rng.normal(pause_mean_ms, pause_std_ms), 200.0, 1500.0))
        else:
            d = gaussian_delay(mean_ms, std_ms, clamp_min_ms, clamp_max_ms, rng=rng)
        delays.append(d)
    return delays
