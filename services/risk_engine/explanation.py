"""Explanation for the WHY panel.

This is a TRANSPARENT WEIGHTED CONTRIBUTION, not SHAP.

Every contribution is literally `component_score x component_weight`, and the
four of them sum exactly to the risk score. That is an arithmetic decomposition
of a linear model, which is honest and auditable — but it is not a
model-agnostic attribution method, and the UI must not call it SHAP until a
real ML model with a real explainer exists.
"""
from __future__ import annotations

from .scoring import COMPONENT_LABELS, COMPONENT_WEIGHTS


def _n(value, default=0.0):
    """Missing inputs read as 0 in the score, so they must read as 0 here too."""
    return default if value is None else value


EVIDENCE = {
    "hazard": lambda r: (
        f"Mean susceptibility {_n(r.get('mean_hazard')):.0f}/100 across the settlement, "
        f"peaking at {_n(r.get('max_hazard')):.0f}"
    ),
    "exposure": lambda r: (
        f"{int(_n(r.get('exposed_population'))):,} of {int(_n(r.get('population'))):,} residents in "
        f"High or Very High susceptibility terrain "
        f"({_n(r.get('exposed_area_percent')):.0f}% of the settlement area)"
    ),
    "vulnerability": lambda r: (
        f"Settlement site averages {_n(r.get('site_slope_mean_deg')):.0f} deg slope; "
        f"classified as {r.get('place') or 'village'}"
    ),
    "response": lambda r: (
        f"{_n(r.get('dist_to_major_road_m')) / 1000:.1f} km to a major road, "
        f"{_n(r.get('dist_to_health_m')) / 1000:.1f} km to health care"
    ),
}


def explain(rec: dict, scored: dict) -> list[dict]:
    """Return contributions, largest first, each with its supporting evidence."""
    out = []
    for name, value in scored["contributions"].items():
        out.append({
            "id": name,
            "label": COMPONENT_LABELS[name],
            "component_score": scored["components"][name],
            "weight": COMPONENT_WEIGHTS[name],
            "contribution": value,
            "evidence": EVIDENCE[name](rec),
        })
    out.sort(key=lambda d: -d["contribution"])
    return out


def method_note() -> str:
    return ("Transparent weighted contribution: each factor's score multiplied by its "
            "documented weight. Contributions sum exactly to the risk score. "
            "Not SHAP; no machine-learning model is involved.")
