"""Bhoomi Raksha analytical API.

    React -> IntelligenceProvider -> FastAPI -> engines -> processed geodata

The browser never computes an analytical result and never reads a raster.
Everything here is served from the processed pilot artefacts, except scenarios,
which re-run the pipeline in-process (~0.5 s) and are explicitly a compute call.
"""
from __future__ import annotations

import math
import sys
import time
from datetime import datetime, timezone

from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

sys.path.insert(0, ".")

from apps.api import schemas as S  # noqa: E402
from apps.api.store import (  # noqa: E402
    ACTIVE_HAZARD, DISCLAIMER, LIMITATIONS, MODEL_VERSION, PROVENANCE,
    capacity_constraints, haversine_km, load,
)
from services.risk_engine import explain, score_habitation  # noqa: E402
from services.risk_engine.explanation import method_note  # noqa: E402
from services.optimization_engine import OptimizationConfig, solve_allocation  # noqa: E402
from services.scenario_engine import ScenarioParameters, run_scenario  # noqa: E402

app = FastAPI(title="Bhoomi Raksha", version=MODEL_VERSION,
              description="Geospatial decision intelligence for the Kangra landslide pilot.")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

RECOMMENDATION = {
    "critical": "Relocation assessment",
    "high": "Relocation assessment",
    "monitor": "Monitor and prepare",
    "safe": "Routine monitoring",
}


def _display(x: float) -> int:
    """Half-up rounding, matching the browser's Math.round, so 69.5 never shows
    as 69 in one place and 70 in another."""
    return int(math.floor(float(x) + 0.5))


def _hazard_model() -> dict:
    return load()["hazard_models"][ACTIVE_HAZARD]


def _summary(h: dict) -> dict:
    return {
        "id": h["id"], "name": h["name"], "place": h.get("place"),
        "lon": h["lon"], "lat": h["lat"],
        "population": int(h.get("population") or 0),
        "exposed_population": int(h.get("exposed_population") or 0),
        "exposed_area_percent": h.get("exposed_area_percent"),
        "mean_hazard": h.get("mean_hazard"), "max_hazard": h.get("max_hazard"),
        "risk_score": h["risk_score"], "level": h["level"],
        "priority_rank": int(h.get("priority_rank") or 0),
        "priority_score": float(h.get("priority_score") or 0.0),
        "confidence": h["confidence"],
        "hazard_type": ACTIVE_HAZARD,
    }


@app.on_event("startup")
def _warm() -> None:
    """Load the artefacts and precompute the zero-delta baseline at start-up.

    Both are otherwise paid for inside the first request that needs them, which
    put a multi-second stall on the analyst's first scenario click. Warming
    here keeps the demo's first interaction as fast as its tenth.
    """
    load()
    _baseline_scenario()


@app.get("/api/health")
def health():
    d = load()
    return {"status": "ok", "model_version": MODEL_VERSION,
            "habitations": len(d["habitations"]), "candidates": len(d["candidates"]),
            "loaded_at": d["loaded_at"]}


@app.get("/api/region", response_model=S.RegionSummary)
def region():
    d = load()
    ex = d["exposure"]
    return S.RegionSummary(
        hazard_type=ACTIVE_HAZARD, hazard_model=S.HazardModel(**_hazard_model()),
        name="Kangra district", code="HP-KAN", state="Himachal Pradesh",
        area_km2=round(d["grid"]["area_km2"], 0),
        primary_hazard="Landslide susceptibility",
        settlements=len(d["habitations"]),
        district_population=ex["district"]["population"],
        district_exposed_population=ex["district"]["exposed_population"],
        settlement_population=ex["settlements"]["population"],
        settlement_exposed_population=ex["settlements"]["exposed_population"],
        levels=d["levels"],
        red_zone_area_km2=d["red_area_km2"],
        candidate_sites=len(d["candidates"]),
        feasible_sites=sum(1 for c in d["candidates"] if c["screening_status"] == "FEASIBLE"),
        updated_at=d["loaded_at"], model_version=MODEL_VERSION,
        provenance=[S.Provenance(**p) for p in PROVENANCE],
        disclaimer=DISCLAIMER,
    )


@app.get("/api/habitations", response_model=list[S.HabitationSummary])
def habitations(limit: int = Query(400, ge=1, le=2000),
                level: str | None = None):
    d = load()
    rows = d["habitations"]
    if level:
        wanted = set(level.split(","))
        rows = [h for h in rows if h["level"] in wanted]
    return [S.HabitationSummary(**_summary(h)) for h in rows[:limit]]


@app.get("/api/priority", response_model=list[S.HabitationSummary])
def priority(limit: int = Query(25, ge=1, le=200)):
    d = load()
    return [S.HabitationSummary(**_summary(h)) for h in d["habitations"][:limit]]


@app.get("/api/hazard/red-zones")
def red_zones(min_area_km2: float = Query(0.1, ge=0.0)):
    d = load()
    feats = [f for f in d["red_zones"]["features"]
             if f["properties"].get("area_km2", 0) >= min_area_km2]
    return {"type": "FeatureCollection", "features": feats,
            "meta": {"count": len(feats), "total_area_km2": d["red_area_km2"],
                     "threshold": "susceptibility index >= 60 (High/Very High)",
                     "note": "derived from the susceptibility raster; "
                             "a susceptibility red zone is not an automatic relocation zone"}}


@app.get("/api/hazard/susceptibility")
def susceptibility():
    d = load()
    s = d["susceptibility"]
    return {"model": "transparent weighted overlay",
            "weights": s["weights"], "classes": s["classes"],
            "validated": False,
            "statement": "Susceptibility index, not a probability or a prediction. "
                         "Unvalidated: no landslide inventory was obtainable for Kangra.",
            "factors": [
                {"name": "slope", "weight": 0.45,
                 "normalisation": "piecewise, peaks at 35-45 deg, falls above 55 deg"},
                {"name": "monsoon rainfall", "weight": 0.30, "normalisation": "linear 200-2000 mm"},
                {"name": "local relief", "weight": 0.25, "normalisation": "linear 0-200 m"},
            ]}


def _detail(h: dict) -> dict:
    scored = score_habitation(h)
    factors = explain(h, scored)
    conf, reasons = h["confidence"], h["confidence_reasons"]
    return {
        **_summary(h),
        "hazard_model": _hazard_model(),
        "hazard": {
            "type": ACTIVE_HAZARD,
            "mean_susceptibility": h.get("mean_hazard"),
            "peak_susceptibility": h.get("max_hazard"),
            "hazard_component": scored["components"]["hazard"],
        },
        "risk_display": _display(scored["risk_score"]),
        "site_slope_mean_deg": h.get("site_slope_mean_deg"),
        "dist_to_road_m": h.get("dist_to_road_m"),
        "dist_to_major_road_m": h.get("dist_to_major_road_m"),
        "dist_to_health_m": h.get("dist_to_health_m"),
        "footprint_source": h.get("footprint_source", "unknown"),
        "analysed_area_km2": h.get("analysed_area_km2"),
        "components": scored["components"],
        "contributions": scored["contributions"],
        "explanation": {
            "method": "Transparent Weighted Contribution",
            "note": method_note(),
            "contributions": factors,
            "total": scored["risk_score"],
        },
        "data_quality": {
            "confidence": conf, "reasons": reasons,
            "footprint_source": h.get("footprint_source"),
            "population_source": "GHSL GHS-POP R2023A 2020 (modelled, not census)",
            "hazard_validation": "unvalidated - no landslide inventory available",
            "accessibility_method": "Euclidean distance, not network travel time",
        },
        "recommendation": RECOMMENDATION.get(h["level"], "Monitor"),
    }


@app.get("/api/habitations/{habitation_id}", response_model=S.HabitationDetail)
def habitation_detail(habitation_id: str):
    d = load()
    h = d["by_id"].get(habitation_id)
    if not h:
        raise HTTPException(404, f"unknown habitation {habitation_id}")
    return S.HabitationDetail(**_detail(h))


@app.get("/api/risk/{habitation_id}", response_model=S.HabitationDetail)
def risk(habitation_id: str):
    return habitation_detail(habitation_id)


@app.get("/api/exposure/{habitation_id}")
def exposure(habitation_id: str):
    d = load()
    h = d["by_id"].get(habitation_id)
    if not h:
        raise HTTPException(404, f"unknown habitation {habitation_id}")
    return {
        "id": h["id"], "name": h["name"],
        "population": int(h.get("population") or 0),
        "exposed_population": int(h.get("exposed_population") or 0),
        "exposed_area_percent": h.get("exposed_area_percent"),
        "mean_hazard": h.get("mean_hazard"), "max_hazard": h.get("max_hazard"),
        "analysed_area_km2": h.get("analysed_area_km2"),
        "footprint_source": h.get("footprint_source"),
        "method": "susceptibility raster intersected with the settlement's allocated "
                  "cells; exposed population is the GHSL population in cells at "
                  "susceptibility >= 60, not a proportional estimate",
        "district_context": d["exposure"]["district"],
    }


def _site_payload(c: dict, origin: dict | None = None) -> dict:
    out = {
        "candidate_id": c["candidate_id"], "lon": float(c["lon"]), "lat": float(c["lat"]),
        "area_km2": float(c["area_km2"]),
        "mean_susceptibility": float(c["mean_susceptibility"]),
        "max_susceptibility": float(c["max_susceptibility"]),
        "mean_slope_deg": float(c["mean_slope_deg"]),
        "distance_to_road_m": float(c["distance_to_road_m"]),
        "distance_to_major_road_m": float(c["distance_to_major_road_m"]),
        "distance_to_healthcare_m": float(c["distance_to_healthcare_m"]),
        "current_population": int(c["current_population"]),
        "suitability_score": float(c["suitability_score"]),
        "screening_status": c["screening_status"],
        "safety_score": float(c["safety_score"]),
        "terrain_score": float(c["terrain_score"]),
        "road_access_score": float(c["road_access_score"]),
        "healthcare_access_score": float(c["healthcare_access_score"]),
        "effective_capacity": int(c["effective_capacity"]),
        "available_capacity": int(c["available_capacity"]),
        "binding_constraint": c["binding_constraint"],
        "constraints": capacity_constraints(c),
    }
    if origin:
        out["distance_from_habitation_km"] = round(
            haversine_km(origin["lon"], origin["lat"], out["lon"], out["lat"]), 2)
    return out


@app.get("/api/relocation/sites", response_model=list[S.CandidateSite])
def relocation_sites(habitation_id: str | None = None,
                     limit: int = Query(8, ge=1, le=100),
                     status: str = "FEASIBLE"):
    d = load()
    wanted = set(status.split(",")) if status else None
    sites = [c for c in d["candidates"]
             if (not wanted or c["screening_status"] in wanted)
             and c["available_capacity"] > 0]
    origin = d["by_id"].get(habitation_id) if habitation_id else None
    payload = [_site_payload(c, origin) for c in sites]
    if origin:
        # nearest first, then most suitable: relocation should keep communities
        # close to their land unless a nearer site is materially worse
        payload.sort(key=lambda s: (s["distance_from_habitation_km"], -s["suitability_score"]))
    else:
        payload.sort(key=lambda s: -s["suitability_score"])
    return [S.CandidateSite(**s) for s in payload[:limit]]


@app.get("/api/capacity/{site_id}", response_model=S.CandidateSite)
def capacity(site_id: str, habitation_id: str | None = None):
    d = load()
    c = d["by_candidate"].get(site_id)
    if not c:
        raise HTTPException(404, f"unknown site {site_id}")
    origin = d["by_id"].get(habitation_id) if habitation_id else None
    return S.CandidateSite(**_site_payload(c, origin))


OBJECTIVE_TEXT = ("minimise sum over allocations of people x (distance_km + "
                  "(100 - site suitability)/10), plus a large penalty per person "
                  "left unallocated")


@app.post("/api/optimization/run", response_model=S.OptimizationResult)
def optimization_run(req: S.OptimizationRequest):
    d = load()
    rows = d["habitations"]
    if req.habitation_ids:
        wanted = set(req.habitation_ids)
        rows = [h for h in rows if h["id"] in wanted]
    else:
        rows = [h for h in rows if h["level"] in ("critical", "high")]
    sources = [{"id": h["id"], "name": h["name"], "lon": h["lon"], "lat": h["lat"],
                "demand": int(h.get("exposed_population") or 0)} for h in rows]
    sites = [{"candidate_id": c["candidate_id"], "lon": float(c["lon"]), "lat": float(c["lat"]),
              "available_capacity": int(c["available_capacity"]),
              "suitability_score": float(c["suitability_score"]),
              "screening_status": c["screening_status"]} for c in d["candidates"]]
    res = solve_allocation(sources, sites, OptimizationConfig(
        max_distance_km=req.max_distance_km, allow_review_sites=req.allow_review_sites))
    res["objective_description"] = OBJECTIVE_TEXT
    return S.OptimizationResult(**res)


def _scenario_inputs():
    d = load()
    habs = [{"id": h["id"], "name": h["name"], "place": h.get("place"),
             "lon": h["lon"], "lat": h["lat"],
             "site_slope_mean_deg": h.get("site_slope_mean_deg"),
             "dist_to_road_m": h.get("dist_to_road_m"),
             "dist_to_major_road_m": h.get("dist_to_major_road_m"),
             "dist_to_health_m": h.get("dist_to_health_m"),
             "footprint_source": h.get("footprint_source"),
             "analysed_area_km2": h.get("analysed_area_km2"),
             "alloc_index": int(h["alloc_index"])} for h in d["habitations"]]
    habs.sort(key=lambda h: h["alloc_index"])
    cands = [{"candidate_id": c["candidate_id"], "lon": float(c["lon"]), "lat": float(c["lat"]),
              "terrain_score": float(c["terrain_score"]),
              "road_access_score": float(c["road_access_score"]),
              "healthcare_access_score": float(c["healthcare_access_score"]),
              "cap_land": int(c["cap_land"]), "cap_infrastructure": int(c["cap_infrastructure"]),
              "cap_healthcare": int(c["cap_healthcare"]),
              "cap_environmental": int(c["cap_environmental"]),
              "cap_accessibility": int(c["cap_accessibility"]),
              "current_population": int(c["current_population"])} for c in d["candidates"]]
    return habs, cands


@lru_cache(maxsize=1)
def _baseline_scenario():
    """Zero-delta run, cached.

    Both sides of every comparison must come from one code path. Reading the
    baseline from the stored artefacts instead made a zero-delta scenario
    report 342 -> 339 feasible sites, because the pipeline and the scenario
    engine aggregate candidate cells slightly differently at the screening
    boundary. Comparing like with like removes that phantom delta.
    """
    habs, cands = _scenario_inputs()
    return run_scenario(ScenarioParameters(0.0, 0.0, 100.0), habs, cands)


@app.post("/api/scenario/run", response_model=S.ScenarioResponse)
def scenario_run(req: S.ScenarioRequest):
    t0 = time.perf_counter()
    d = load()
    habs, cands = _scenario_inputs()

    scen = run_scenario(ScenarioParameters(
        req.rainfall_delta_percent, req.population_delta_percent,
        req.road_availability_percent), habs, cands)

    base = _baseline_scenario()
    base_levels = base["levels"]
    base_exposed = base["settlement_exposed_population"]
    base_opt = base["optimization"]
    base_feasible = base["feasible_sites"]
    base_capacity = base["total_available_capacity"]

    def delta(label, b, s, unit=""):
        return S.ScenarioDelta(label=label, baseline=round(float(b), 1),
                               scenario=round(float(s), 1),
                               delta=round(float(s) - float(b), 1), unit=unit)

    deltas = [
        delta(f"Critical {_hazard_model()['label'].lower()} risk",
              base_levels.get("critical", 0), scen["levels"].get("critical", 0)),
        delta(f"High {_hazard_model()['label'].lower()} risk",
              base_levels.get("high", 0), scen["levels"].get("high", 0)),
        delta("Exposed population", base_exposed, scen["settlement_exposed_population"], "people"),
        delta("Feasible relocation sites", base_feasible, scen["feasible_sites"]),
        delta("Available capacity", base_capacity, scen["total_available_capacity"], "people"),
        delta("Relocation demand met", base_opt["total_relocated"],
              scen["optimization"]["total_relocated"], "people"),
    ]

    base_by_id = {h["id"]: h for h in base["habitations"]}
    changed = []
    for r in scen["habitations"]:
        b = base_by_id.get(r["id"])
        if b and b["level"] != r["level"]:
            changed.append({"id": r["id"], "name": r["name"],
                            "from": b["level"], "to": r["level"],
                            "risk_baseline": b["risk_score"], "risk_scenario": r["risk_score"]})
    changed.sort(key=lambda c: -c["risk_scenario"])

    opt = dict(scen["optimization"])
    opt["objective_description"] = OBJECTIVE_TEXT

    return S.ScenarioResponse(
        parameters=req, deltas=deltas,
        baseline_levels=base_levels, scenario_levels=scen["levels"],
        changed_habitations=changed[:40],
        top_priority_baseline=base["habitations"][0]["name"],
        top_priority_scenario=scen["habitations"][0]["name"],
        optimization=S.OptimizationResult(**opt),
        propagation_notes=scen["propagation_notes"],
        runtime_ms=int((time.perf_counter() - t0) * 1000),
    )


@app.get("/api/executive-brief/{habitation_id}", response_model=S.ExecutiveBrief)
def executive_brief(habitation_id: str):
    d = load()
    h = d["by_id"].get(habitation_id)
    if not h:
        raise HTTPException(404, f"unknown habitation {habitation_id}")
    detail = _detail(h)

    sites = relocation_sites(habitation_id=habitation_id, limit=1)
    preferred = sites[0] if sites else None

    opt = None
    if h["level"] in ("critical", "high") and (h.get("exposed_population") or 0) > 0:
        res = solve_allocation(
            [{"id": h["id"], "name": h["name"], "lon": h["lon"], "lat": h["lat"],
              "demand": int(h["exposed_population"])}],
            [{"candidate_id": c["candidate_id"], "lon": float(c["lon"]), "lat": float(c["lat"]),
              "available_capacity": int(c["available_capacity"]),
              "suitability_score": float(c["suitability_score"]),
              "screening_status": c["screening_status"]} for c in d["candidates"]],
            OptimizationConfig())
        res["objective_description"] = OBJECTIVE_TEXT
        opt = S.OptimizationResult(**res)

    return S.ExecutiveBrief(
        region="Kangra district, Himachal Pradesh",
        primary_hazard="Landslide susceptibility",
        hazard_type=ACTIVE_HAZARD,
        index_label=_hazard_model()["index_label"],
        habitation=S.HabitationSummary(**_summary(h)),
        observed={
            "population_estimate": detail["population"],
            "population_source": "GHSL GHS-POP 2020 (modelled)",
            "settlement_class": h.get("place"),
            "site_slope_deg": detail["site_slope_mean_deg"],
            "distance_to_major_road_km": round((detail["dist_to_major_road_m"] or 0) / 1000, 1),
            "distance_to_health_km": round((detail["dist_to_health_m"] or 0) / 1000, 1),
        },
        derived={
            "mean_susceptibility": detail["mean_hazard"],
            "max_susceptibility": detail["max_hazard"],
            "exposed_area_percent": detail["exposed_area_percent"],
            "exposed_population": detail["exposed_population"],
            "risk_score": detail["risk_score"],
            "risk_display": detail["risk_display"],
            "risk_class": detail["level"],
            "priority_rank": detail["priority_rank"],
            "contributions": detail["contributions"],
        },
        recommended={
            "action": detail["recommendation"],
            "preferred_site": preferred.candidate_id if preferred else None,
            "effective_capacity": preferred.effective_capacity if preferred else None,
            "available_capacity": preferred.available_capacity if preferred else None,
            "binding_constraint": preferred.binding_constraint if preferred else None,
            "relocation_demand": detail["exposed_population"],
        },
        preferred_site=preferred,
        optimization=opt,
        scenario_note=None,
        data_confidence=detail["data_quality"]["confidence"],
        confidence_reasons=detail["data_quality"]["reasons"],
        limitations=LIMITATIONS,
        disclaimer=DISCLAIMER,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model_version=MODEL_VERSION,
    )
