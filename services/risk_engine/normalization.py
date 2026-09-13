"""Normalisation helpers.

Every scale below uses fixed, documented bounds rather than the observed range
of the current dataset, so a settlement's score does not change just because a
different settlement was added to the study area.
"""
from __future__ import annotations

import math


def linear(value: float, lo: float, hi: float) -> float:
    """Map value onto 0-100 between fixed bounds, clamped."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo))) * 100.0


def inverse_linear(value: float, lo: float, hi: float) -> float:
    """Like `linear` but higher input means a lower score."""
    return 100.0 - linear(value, lo, hi)


def log_scale(value: float, cap: float) -> float:
    """Map a count onto 0-100 logarithmically.

    Population counts span several orders of magnitude — a hamlet of 40 and a
    town of 15,000 are both real. A linear scale would collapse every small
    settlement to nearly zero and make exposure a proxy for town size alone.
    log1p keeps small but non-zero exposure visible while still ranking large
    exposed populations highest.
    """
    if value is None or value <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log1p(value) / math.log1p(cap))) * 100.0


def piecewise(value: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear interpolation, for non-monotonic responses."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    if value <= xs[0]:
        return ys[0]
    if value >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if value <= xs[i]:
            span = xs[i] - xs[i - 1]
            t = 0.0 if span == 0 else (value - xs[i - 1]) / span
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]
