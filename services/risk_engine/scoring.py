"""Risk scoring: hazard x exposure x vulnerability x response difficulty.

    HAZARD ─────┐
    EXPOSURE ───┤
                ├──> weighted sum ──> risk score 0-100 ──> classification
    VULNERAB. ──┤
    RESPONSE ───┘

Every component is computed from a measured input in data/processed/. Nothing
here is hand-assigned per settlement.

WEIGHTS (documented judgement, uncalibrated)
    hazard      0.35  the terrain and rainfall predisposition itself
    exposure    0.30  how many people and how much of the settlement is in it
    vulnerability 0.20  how badly the site and settlement would fare
    response    0.15  how hard it is to reach when something happens

    Hazard and exposure lead because a place is only at risk if the hazard is
    real AND people are in it. Vulnerability and response modulate that.
    These weights are expert judgement, not fitted to observed losses, and
    docs/risk-model.md records that limitation.

VULNERABILITY — WHAT IT DOES AND DOES NOT MEAN
    Socio-economic vulnerability data (housing type, income, age structure,
    SECC) is not openly available per settlement, so this is explicitly a
    *terrain-and-service* vulnerability proxy built from:
        - mean slope of the settlement site
        - settlement class, as a proxy for service provision
    It must never be presented as social vulnerability.
"""
from __future__ import annotations

from .normalization import inverse_linear, linear, log_scale, piecewise

COMPONENT_WEIGHTS = {
    "hazard": 0.35,
    "exposure": 0.30,
    "vulnerability": 0.20,
    "response": 0.15,
}

# Smaller settlements have thinner local services and slower self-recovery.
CLASS_SERVICE_PENALTY = {
    "city": 10.0, "town": 25.0, "suburb": 35.0, "village": 55.0, "hamlet": 70.0,
}

# Exposed-population cap for the log scale: the largest exposed population
# observed in the Kangra pilot is ~1,400, so 5,000 leaves headroom without
# saturating every settlement.
EXPOSED_POP_CAP = 5000.0


# Hazard component = weighted mean/peak of the settlement's landslide
# susceptibility. Named so the API can show the formula instead of restating it.
HAZARD_MEAN_WEIGHT = 0.75
HAZARD_PEAK_WEIGHT = 0.25


def _hazard(rec: dict) -> float:
    """Susceptibility already sits on 0-100; the mean over the footprint is the
    settlement's ambient hazard, and the max captures a dangerous edge."""
    mean_h = rec.get("mean_hazard") or 0.0
    max_h = rec.get("max_hazard") or 0.0
    return HAZARD_MEAN_WEIGHT * mean_h + HAZARD_PEAK_WEIGHT * max_h


def _exposure(rec: dict) -> float:
    """How much of the settlement, and how many people, sit in hazardous ground."""
    area = linear(rec.get("exposed_area_percent") or 0.0, 0.0, 60.0)
    people = log_scale(rec.get("exposed_population") or 0.0, EXPOSED_POP_CAP)
    return 0.5 * area + 0.5 * people


def _vulnerability(rec: dict) -> float:
    """Terrain-and-service vulnerability proxy. Not social vulnerability."""
    # Buildings and roads on steeper ground are harder to found and to hold.
    slope_term = piecewise(rec.get("site_slope_mean_deg") or 0.0,
                           [0, 5, 15, 25, 40], [0, 15, 55, 85, 100])
    service_term = CLASS_SERVICE_PENALTY.get(rec.get("place") or "village", 55.0)
    return 0.6 * slope_term + 0.4 * service_term


def _response(rec: dict) -> float:
    """How hard the settlement is to reach. Higher means harder."""
    major = linear(rec.get("dist_to_major_road_m") or 0.0, 500.0, 12000.0)
    health = linear(rec.get("dist_to_health_m") or 0.0, 1000.0, 15000.0)
    local = linear(rec.get("dist_to_road_m") or 0.0, 100.0, 2000.0)
    return 0.45 * major + 0.35 * health + 0.20 * local


COMPONENTS = {
    "hazard": _hazard,
    "exposure": _exposure,
    "vulnerability": _vulnerability,
    "response": _response,
}

# Human-readable labels used by the WHY panel.
COMPONENT_LABELS = {
    "hazard": "Hazard",
    "exposure": "Exposure",
    "vulnerability": "Vulnerability (terrain & service proxy)",
    "response": "Response difficulty (distance proxy)",
}


def _confidence(rec: dict) -> tuple[float, list[str]]:
    """Confidence reflects input quality, not model certainty.

    The model is uncalibrated either way; this only says how much to trust the
    inputs that went into this particular settlement.
    """
    score = 1.0
    caveats: list[str] = []
    if rec.get("footprint_source") != "osm_polygon":
        score -= 0.20
        caveats.append("settlement extent approximated by buffer, not surveyed")
    if (rec.get("analysed_area_km2") or 0) < 0.05:
        score -= 0.10
        caveats.append("very small analysed area")
    if rec.get("dist_to_health_m") is None:
        score -= 0.10
        caveats.append("no mapped health facility for distance measurement")
    # The hazard layer itself is unvalidated for every settlement.
    score -= 0.15
    caveats.append("hazard layer not validated against a landslide inventory")
    return max(0.0, round(score, 2)), caveats


def score_habitation(rec: dict) -> dict:
    """Score one settlement. `rec` is a row from habitations.geojson properties."""
    components = {name: round(fn(rec), 1) for name, fn in COMPONENTS.items()}
    contributions = {
        name: round(components[name] * COMPONENT_WEIGHTS[name], 1)
        for name in components
    }
    risk = round(sum(contributions.values()), 1)
    confidence, caveats = _confidence(rec)
    return {
        "risk_score": risk,
        "components": components,
        "contributions": contributions,
        "weights": COMPONENT_WEIGHTS,
        "confidence": confidence,
        "caveats": caveats,
    }
