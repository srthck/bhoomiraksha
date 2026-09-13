"""In-memory analytical store.

Loads the processed pilot artefacts once at start-up and answers queries from
memory. The API never shells out to a script and never recomputes a raster on
a request path except for scenarios, which are explicitly a compute endpoint.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache

from services.risk_engine.scoring import (  # noqa: E402
    COMPONENT_LABELS, COMPONENT_WEIGHTS, HAZARD_MEAN_WEIGHT, HAZARD_PEAK_WEIGHT,
)

DATA = os.environ.get("BR_DATA", "data/processed")

# ---------------------------------------------------------------------------
# Hazard-specific models.
#
# Every risk number the product shows is a risk OF something. The hazard type
# travels with the number so no screen can present a bare "risk index".
#
# Only hazards with a real, hazard-specific pipeline are registered. Earthquake
# and flood are deliberately absent: registering them would invite reuse of the
# landslide formula, and an earthquake score built from slope and rainfall
# would be fabricated. A future hazard enters here only with its own hazard
# layer (e.g. seismic ground shaking, flood depth) and its own exposure and
# vulnerability terms.
# ---------------------------------------------------------------------------
ACTIVE_HAZARD = "landslide"
BASIS_LABELS = {"slope": "Slope", "rainfall": "Monsoon rainfall", "relief": "Local relief"}
RISK_MEANING = ("Composite landslide risk score derived from hazard susceptibility, "
                "exposure, vulnerability and response difficulty. A decision-support "
                "index, not the probability of a landslide occurring.")


def _landslide_model(susc_summary: dict) -> dict:
    weights = susc_summary["weights"]  # written by b01_susceptibility; not restated here
    return {
        "type": "landslide",
        "label": "Landslide",
        "index_label": "Landslide risk index",
        "susceptibility_label": "Landslide susceptibility",
        "model_name": "Terrain + Rainfall + Local Relief",
        "method": "Transparent weighted overlay (analytical baseline)",
        "assessment": "Current baseline",
        "basis": [{"factor": k, "label": BASIS_LABELS.get(k, k), "weight": float(v)}
                  for k, v in weights.items()],
        "hazard_mean_weight": HAZARD_MEAN_WEIGHT,
        "hazard_peak_weight": HAZARD_PEAK_WEIGHT,
        "risk_weights": dict(COMPONENT_WEIGHTS),
        "risk_labels": dict(COMPONENT_LABELS),
        "validated": False,
        "meaning": RISK_MEANING,
    }
MODEL_VERSION = "kangra-pilot-2026.09.10"

DISCLAIMER = ("Decision support only - not an autonomous relocation order. "
              "Susceptibility is an unvalidated index, not a prediction.")

LIMITATIONS = [
    "Landslide susceptibility is unvalidated: no landslide inventory was obtainable for Kangra.",
    "Susceptibility is a relative index, not a probability or a forecast.",
    "Population is GHSL modelled population (2020), not census enumeration.",
    "1,045 of 1,183 settlement footprints are class-based buffers, not surveyed extents.",
    "Accessibility is straight-line distance, not road-network travel time.",
    "Rainfall is a WorldClim 1970-2000 climatology at ~4.6 km native resolution.",
    "The district boundary is a third-party GADM-derived mirror, not Survey of India.",
    "Vulnerability is a terrain-and-service proxy, not social vulnerability.",
]

PROVENANCE = [
    {"source": "AWS Terrain Tiles (Mapzen), SRTM-derived, zoom 12",
     "source_resolution": "~26 m/px at 32N, resampled to 30 m",
     "processing": "mosaic -> EPSG:32643 -> plausibility mask -> clip -> Horn slope",
     "validation_status": "max elevation 5,981 m matches Hanuman Tibba (5,982 m)",
     "proxy": False, "limitations": ["surface model: includes canopy and buildings"]},
    {"source": "WorldClim 2.1 monthly precipitation",
     "source_resolution": "2.5 arc-minutes (~4.6 km)",
     "processing": "Jun-Sep sum, bilinear resample to the 30 m analysis grid",
     "validation_status": "district max 1,983 mm matches Dharamshala monsoon",
     "proxy": False,
     "limitations": ["1970-2000 climatology, not current season",
                     "resampling interpolates; it does not add resolution"]},
    {"source": "GHSL GHS-POP R2023A epoch 2020",
     "source_resolution": "100 m Mollweide",
     "processing": "counts -> density -> reproject -> counts (total preserving)",
     "validation_status": "district total 1,652,806 vs Census 2011 1,510,075 (+9.5% over ~9 years)",
     "proxy": True, "limitations": ["modelled redistribution, not census enumeration"]},
    {"source": "OpenStreetMap (ODbL 1.0)",
     "source_resolution": "vector, contributor dependent",
     "processing": "Overpass bbox query, clipped to district",
     "validation_status": "1,183 place nodes, 5,959 km road, 209 health facilities",
     "proxy": False,
     "limitations": ["rural coverage uneven", "health facility coverage incomplete"]},
    {"source": "GADM-derived district boundary (geohacker/india mirror)",
     "source_resolution": "generalised vector",
     "processing": "selected NAME_2=Kangra",
     "validation_status": "area 5,704 km2 vs published ~5,739 km2 (-0.6%)",
     "proxy": False, "limitations": ["not an official Survey of India boundary"]},
]


def _read(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _props(fc):
    out = []
    for f in fc["features"]:
        p = dict(f["properties"])
        g = f["geometry"]
        if g and g["type"] == "Point":
            p["lon"], p["lat"] = g["coordinates"][:2]
        out.append(p)
    return out


def _centroid(geom):
    """Cheap representative point; adequate for distance ranking on a district."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _confidence(rec) -> tuple[str, list[str]]:
    """Explainable data-quality grade. Never a fabricated percentage."""
    reasons = ["hazard model is unvalidated (no landslide inventory)",
               "rainfall input is ~4.6 km climatology"]
    penalty = 2
    if rec.get("footprint_source") != "osm_polygon":
        reasons.append("settlement extent is an approximated buffer")
        penalty += 1
    else:
        reasons.append("settlement extent is a mapped OSM polygon")
    reasons.append("accessibility is straight-line distance, not travel time")
    penalty += 1
    if (rec.get("analysed_area_km2") or 0) < 0.05:
        reasons.append("very small analysed area")
        penalty += 1
    grade = "HIGH" if penalty <= 2 else "MEDIUM" if penalty <= 4 else "LOW"
    return grade, reasons


@lru_cache(maxsize=1)
def load():
    hab_fc = _read("habitation_risk.geojson")
    cand_fc = _read("candidate_capacity.geojson")
    exposure = _read("exposure_summary.json")
    susc = _read("susceptibility_summary.json")
    cand_meta = _read("candidate_summary.json")
    grid = _read("grid.json")
    optimisation = _read("optimization_baseline.json")

    habitations = []
    for f in hab_fc["features"]:
        p = dict(f["properties"])
        lon, lat = _centroid(f["geometry"])
        conf, reasons = _confidence(p)
        # OSM place nodes are not always named. Showing the raw
        # "unnamed_6591851722" placeholder in a decision brief reads as a bug;
        # this keeps it honest ("Unnamed hamlet") and still identifiable.
        name = p.get("name") or ""
        if name.startswith("unnamed_"):
            name = f"Unnamed {p.get('place') or 'settlement'} {name.split('_')[-1][-4:]}"
        habitations.append({
            **p,
            "name": name,
            "id": f"osm-{int(p['osm_id'])}",
            "lon": round(lon, 5), "lat": round(lat, 5),
            "confidence": conf, "confidence_reasons": reasons,
        })
    habitations.sort(key=lambda h: h.get("priority_rank", 10 ** 6))

    candidates = []
    for f in cand_fc["features"]:
        p = dict(f["properties"])
        candidates.append(p)

    red = _read("red_zones.geojson")
    red_area = sum(f["properties"].get("area_km2", 0) for f in red["features"])

    levels = {}
    for h in habitations:
        levels[h["level"]] = levels.get(h["level"], 0) + 1

    return {
        "habitations": habitations,
        "by_id": {h["id"]: h for h in habitations},
        "candidates": candidates,
        "by_candidate": {c["candidate_id"]: c for c in candidates},
        "red_zones": red,
        "red_area_km2": round(red_area, 1),
        "exposure": exposure,
        "susceptibility": susc,
        "candidate_meta": cand_meta,
        "grid": grid,
        "optimization": optimisation,
        "levels": levels,
        "hazard_models": {"landslide": _landslide_model(susc)},
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


CAPACITY_DERIVATION = {
    "land": "DERIVED from the slope raster (developable hectares) x 100 persons/ha (CURATED_PILOT_ASSUMPTION)",
    "infrastructure": "CURATED_PILOT_ASSUMPTION ceiling scaled by DERIVED distance to a major road",
    "healthcare": "DERIVED from OSM facilities within 10 km using IPHS service norms, minus existing population load",
    "environmental": "Water availability proxy DERIVED from the rainfall raster at 55 lpcd (Jal Jeevan Mission), runoff 0.15 (CURATED_PILOT_ASSUMPTION); not a measured water yield",
    "accessibility": "CURATED_PILOT_ASSUMPTION ceiling scaled by DERIVED distance to the nearest road",
}


def capacity_constraints(c: dict) -> list[dict]:
    binding = c.get("binding_constraint")
    return [{
        "name": k,
        "capacity": int(c.get(f"cap_{k}", 0)),
        "derivation": CAPACITY_DERIVATION[k],
        "is_binding": k == binding,
    } for k in ("land", "infrastructure", "healthcare", "environmental", "accessibility")]
