"""Risk classification bands.

Breaks are product decisions, documented in docs/risk-model.md. They are not
derived from a statistical distribution — they define what the operator is
being asked to treat as urgent.
"""
from __future__ import annotations

CLASS_BREAKS = [
    (75.0, 101.0, "critical"),
    (60.0, 75.0, "high"),
    (40.0, 60.0, "monitor"),
    (0.0, 40.0, "safe"),
]


def classify(score: float) -> str:
    for lo, hi, label in CLASS_BREAKS:
        if lo <= score < hi:
            return label
    return "safe"
