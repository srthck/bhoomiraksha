"""Scenario propagation through the real analytical pipeline.

A scenario does not nudge dashboard numbers. It re-runs the chain:

    rainfall / population / road availability
        -> susceptibility raster        (recomputed cell by cell)
        -> settlement exposure          (re-accumulated over the allocation)
        -> risk + classification        (risk engine re-run)
        -> priority                     (re-ranked)
        -> candidate suitability        (re-screened)
        -> carrying capacity            (re-derived)
        -> constrained optimisation     (re-solved)

HOW EACH CONTROL PROPAGATES

  rainfall_delta_percent
      Scales the monsoon rainfall raster, which is a real input to the
      susceptibility overlay. Everything downstream moves as a consequence.
      This is genuine propagation.

  population_delta_percent
      Scales the GHSL population grid, changing exposed population, the
      exposure term of risk, and therefore relocation demand.

  road_availability_percent
      There is no network model here, so link removal cannot be simulated.
      Reduced availability is modelled as an inflation of effective distance:
      effective_distance = measured_distance * (100 / availability).
      That is a documented transformation, not a measurement, and it is
      labelled as such in the result payload.

WHAT DOES NOT PROPAGATE (stated, not faked)
      Slope, relief and elevation are fixed terrain and do not respond to any
      of these controls. Health-facility locations are fixed. Nothing here
      models landslide *occurrence* — only susceptibility.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import rasterio

from services.risk_engine import classify, explain, score_habitation
from services.optimization_engine import OptimizationConfig, solve_allocation

DATA = "data/processed"
HIGH_BREAK = 60.0
W_SUSC = {"slope": 0.45, "rainfall": 0.30, "relief": 0.25}
RAIN_LO, RAIN_HI = 200.0, 2000.0
RELIEF_HI = 200.0


@dataclass
class ScenarioParameters:
    rainfall_delta_percent: float = 0.0
    population_delta_percent: float = 0.0
    road_availability_percent: float = 100.0


def _slope_response(deg):
    x = [0, 10, 20, 35, 45, 60, 90]
    y = [0.00, 0.10, 0.45, 0.95, 1.00, 0.70, 0.35]
    return np.interp(deg, x, y)


@lru_cache(maxsize=1)
def _grids():
    """Load every raster once. Factor arrays that never change are precomputed."""
    def read(name):
        with rasterio.open(os.path.join(DATA, name)) as s:
            return s.read(1)

    slope = read("slope.tif")
    relief = read("relief.tif")
    rain = read("rainfall_monsoon.tif")
    pop = read("population.tif")
    alloc = read("allocation.tif")

    valid = np.isfinite(slope) & np.isfinite(relief) & np.isfinite(rain)
    f_slope = _slope_response(np.where(valid, slope, 0)).astype(np.float32)
    f_relief = np.clip(np.where(valid, relief, 0) / RELIEF_HI, 0, 1).astype(np.float32)

    v = valid.ravel()
    a = alloc.ravel()
    # Match b02_exposure exactly: only cells with a real susceptibility value
    # count. Including out-of-district buffer overhang as zero would deflate
    # every settlement's mean hazard and silently disagree with the pipeline.
    sel = (a > 0) & v
    idx = (a[sel] - 1).astype(np.int64)

    with open(os.path.join(DATA, "candidate_zones.npy"), "rb") as fh:
        cand_zone = np.load(fh)
    ca = cand_zone.ravel()
    csel = (ca > 0) & v
    cidx = (ca[csel] - 1).astype(np.int64)

    return {
        "valid": valid, "f_slope": f_slope, "f_relief": f_relief,
        "rain": np.where(valid, rain, 0).astype(np.float32),
        "pop": np.nan_to_num(pop).astype(np.float32),
        "sel": sel, "idx": idx,
        "csel": csel, "cidx": cidx,
        "shape": slope.shape,
    }


def _susceptibility(g, rainfall_scale):
    rain = g["rain"] * rainfall_scale
    f_rain = np.clip((rain - RAIN_LO) / (RAIN_HI - RAIN_LO), 0, 1)
    idx = (W_SUSC["slope"] * g["f_slope"]
           + W_SUSC["rainfall"] * f_rain
           + W_SUSC["relief"] * g["f_relief"])
    out = np.where(g["valid"], idx * 100.0, np.nan).astype(np.float32)
    return out


def run_scenario(params: ScenarioParameters, habitations: list[dict],
                 candidates: list[dict]) -> dict:
    """Recompute the chain under `params`. Returns scenario-side outputs only;
    the caller pairs them with the stored baseline for comparison."""
    g = _grids()
    rain_scale = 1.0 + params.rainfall_delta_percent / 100.0
    pop_scale = 1.0 + params.population_delta_percent / 100.0
    road_inflate = 100.0 / max(params.road_availability_percent, 1.0)

    susc = _susceptibility(g, rain_scale)
    sv = susc.ravel()[g["sel"]]
    pv = g["pop"].ravel()[g["sel"]] * pop_scale
    idx = g["idx"]
    n = len(habitations)

    cells = np.bincount(idx, minlength=n)
    sum_s = np.bincount(idx, weights=np.nan_to_num(sv), minlength=n)
    max_s = np.zeros(n)
    np.maximum.at(max_s, idx, np.nan_to_num(sv))
    high = np.bincount(idx, weights=(sv >= HIGH_BREAK).astype(float), minlength=n)
    tot_p = np.bincount(idx, weights=pv, minlength=n)
    exp_p = np.bincount(idx, weights=pv * (sv >= HIGH_BREAK), minlength=n)

    scored = []
    for i, h in enumerate(habitations):
        rec = dict(h)
        rec["mean_hazard"] = round(float(sum_s[i] / max(cells[i], 1)), 1)
        rec["max_hazard"] = round(float(max_s[i]), 1)
        rec["exposed_area_percent"] = round(float(100 * high[i] / max(cells[i], 1)), 1)
        rec["population"] = int(round(tot_p[i]))
        rec["exposed_population"] = int(round(exp_p[i]))
        rec["dist_to_major_road_m"] = (h.get("dist_to_major_road_m") or 0) * road_inflate
        rec["dist_to_health_m"] = (h.get("dist_to_health_m") or 0) * road_inflate
        rec["dist_to_road_m"] = (h.get("dist_to_road_m") or 0) * road_inflate
        s = score_habitation(rec)
        scored.append({
            "id": h["id"], "name": h["name"], "place": h.get("place"),
            "mean_hazard": rec["mean_hazard"], "max_hazard": rec["max_hazard"],
            "exposed_area_percent": rec["exposed_area_percent"],
            "population": rec["population"], "exposed_population": rec["exposed_population"],
            "risk_score": s["risk_score"], "level": classify(s["risk_score"]),
            "components": s["components"], "contributions": s["contributions"],
            "lon": h["lon"], "lat": h["lat"],
        })

    # priority, same formula as the baseline pipeline
    from services.risk_engine.normalization import log_scale
    for r in scored:
        r["priority_score"] = round(
            0.45 * r["risk_score"]
            + 0.35 * log_scale(r["exposed_population"], 5000.0)
            + 0.20 * r["components"]["response"], 1)
    scored.sort(key=lambda r: -r["priority_score"])
    for rank, r in enumerate(scored, start=1):
        r["priority_rank"] = rank

    # candidate re-screening under the new susceptibility surface
    csv_ = susc.ravel()[g["csel"]]
    cidx = g["cidx"]
    m = len(candidates)
    ccells = np.bincount(cidx, minlength=m)
    csum = np.bincount(cidx, weights=np.nan_to_num(csv_), minlength=m)
    cmax = np.zeros(m)
    np.maximum.at(cmax, cidx, np.nan_to_num(csv_))

    sites = []
    for j, c in enumerate(candidates):
        mean_s = float(csum[j] / max(ccells[j], 1))
        max_s_c = float(cmax[j])
        safety = max(0.0, 100 - mean_s)
        suit = round(0.40 * safety
                     + 0.25 * c["terrain_score"]
                     + 0.20 * max(0.0, c["road_access_score"] - (road_inflate - 1) * 100)
                     + 0.15 * c["healthcare_access_score"], 1)
        status = ("FEASIBLE" if suit >= 60 and max_s_c < 60
                  else "REVIEW" if suit >= 45 else "REJECTED")
        # capacity: the accessibility ceiling degrades with road availability;
        # land, water and healthcare limits are unchanged by these controls.
        access_cap = c["cap_accessibility"] / road_inflate
        eff = min(c["cap_land"], c["cap_infrastructure"], c["cap_healthcare"],
                  c["cap_environmental"], access_cap)
        cur = c["current_population"] * pop_scale
        sites.append({
            "candidate_id": c["candidate_id"], "lon": c["lon"], "lat": c["lat"],
            "mean_susceptibility": round(mean_s, 1), "max_susceptibility": round(max_s_c, 1),
            "suitability_score": suit, "screening_status": status,
            "effective_capacity": int(round(eff)),
            "available_capacity": int(max(0, round(eff - cur))),
        })

    demand = [{"id": r["id"], "name": r["name"], "lon": r["lon"], "lat": r["lat"],
               "demand": r["exposed_population"]}
              for r in scored if r["level"] in ("critical", "high") and r["exposed_population"] > 0]
    opt = solve_allocation(demand, sites, OptimizationConfig())

    levels = {}
    for r in scored:
        levels[r["level"]] = levels.get(r["level"], 0) + 1

    return {
        "parameters": {
            "rainfall_delta_percent": params.rainfall_delta_percent,
            "population_delta_percent": params.population_delta_percent,
            "road_availability_percent": params.road_availability_percent,
        },
        "habitations": scored,
        "levels": levels,
        "settlement_exposed_population": int(sum(r["exposed_population"] for r in scored)),
        "sites": sites,
        "feasible_sites": sum(1 for s in sites if s["screening_status"] == "FEASIBLE"),
        "total_available_capacity": int(sum(s["available_capacity"] for s in sites
                                            if s["screening_status"] == "FEASIBLE")),
        "optimization": opt,
        "propagation_notes": [
            "rainfall scales the susceptibility input directly",
            "population scales the exposure and demand inputs directly",
            "road availability is modelled as inflated effective distance, not link removal",
            "slope, relief and elevation are fixed terrain and do not respond",
        ],
    }
