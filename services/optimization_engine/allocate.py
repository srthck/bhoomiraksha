"""Constrained relocation allocation, solved with OR-Tools.

This replaces the previous greedy first-fit loop. Greedy assignment is not
optimisation: it takes whatever site comes first in list order and can strand
demand that a different ordering would have served. The UI must not describe
its output as "optimal", and now it does not have to.

DECISION VARIABLES
    x[i][j]  people relocated from habitation i to candidate site j  (integer)
    u[i]     people from habitation i left unallocated               (integer)

CONSTRAINTS
    demand        sum_j x[i][j] + u[i] == demand_i
    capacity      sum_i x[i][j] <= available_capacity_j
    safety        x[i][j] == 0 unless site j passed screening as FEASIBLE
    accessibility x[i][j] == 0 when the site is beyond max_distance_km
    non-negative  x, u >= 0

    `u` is a slack variable, not a fudge: without it an over-subscribed or
    isolated habitation makes the whole model INFEASIBLE and the operator
    learns nothing. With it, the solver still returns an optimal assignment and
    reports exactly how many people could not be placed.

OBJECTIVE (minimise)
    sum over i,j of x[i][j] * ( w_distance * distance_km
                              + w_suitability * (100 - suitability_j) / 10 )
    + unmet_penalty * sum_i u[i]

    Two readable terms: how far people move, and how good the destination is.
    The unmet penalty sits far above any achievable per-person cost, so the
    solver always places a person if it legally can, and leaves demand unmet
    only when a constraint genuinely forbids placement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.linear_solver import pywraplp


@dataclass
class OptimizationConfig:
    max_distance_km: float = 40.0
    w_distance: float = 1.0
    w_suitability: float = 1.0
    unmet_penalty: float = 1000.0
    allow_review_sites: bool = False
    solver_name: str = "CBC"
    time_limit_s: float = 30.0
    notes: list[str] = field(default_factory=list)


def _haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def solve_allocation(habitations: list[dict], sites: list[dict],
                     config: OptimizationConfig | None = None) -> dict:
    """habitations: id, name, lon, lat, demand
       sites:       candidate_id, lon, lat, available_capacity,
                    suitability_score, screening_status
    """
    cfg = config or OptimizationConfig()

    allowed_status = {"FEASIBLE"} | ({"REVIEW"} if cfg.allow_review_sites else set())
    sinks = [s for s in sites
             if s.get("screening_status") in allowed_status
             and (s.get("available_capacity") or 0) > 0]
    sources = [h for h in habitations if (h.get("demand") or 0) > 0]

    if not sources:
        return {"solver_status": "NO_DEMAND", "allocations": [], "total_relocated": 0,
                "unallocated_population": 0, "unmet_by_source": [], "site_utilization": [],
                "objective_value": 0.0, "constraint_summary": [],
                "sources": 0, "sinks": len(sinks)}
    if not sinks:
        return {"solver_status": "INFEASIBLE", "allocations": [], "total_relocated": 0,
                "unallocated_population": int(sum(h["demand"] for h in sources)),
                "unmet_by_source": [], "site_utilization": [], "objective_value": 0.0,
                "constraint_summary": ["no site passed safety screening with spare capacity"],
                "sources": len(sources), "sinks": 0}

    solver = pywraplp.Solver.CreateSolver(cfg.solver_name)
    if solver is None:
        raise RuntimeError(f"OR-Tools solver {cfg.solver_name} unavailable")
    solver.SetTimeLimit(int(cfg.time_limit_s * 1000))

    dist = [[_haversine_km(h["lon"], h["lat"], s["lon"], s["lat"]) for s in sinks]
            for h in sources]
    eligible = [[d <= cfg.max_distance_km for d in row] for row in dist]

    x = {}
    for i, h in enumerate(sources):
        for j in range(len(sinks)):
            if eligible[i][j]:
                x[i, j] = solver.IntVar(0, int(h["demand"]), f"x_{i}_{j}")
    u = [solver.IntVar(0, int(h["demand"]), f"u_{i}") for i, h in enumerate(sources)]

    for i, h in enumerate(sources):
        terms = [x[i, j] for j in range(len(sinks)) if (i, j) in x]
        solver.Add(solver.Sum(terms) + u[i] == int(h["demand"]))

    for j, s in enumerate(sinks):
        terms = [x[i, j] for i in range(len(sources)) if (i, j) in x]
        if terms:
            solver.Add(solver.Sum(terms) <= int(s["available_capacity"]))

    obj = []
    for (i, j), var in x.items():
        cost = (cfg.w_distance * dist[i][j]
                + cfg.w_suitability * (100.0 - float(sinks[j]["suitability_score"])) / 10.0)
        obj.append(cost * var)
    obj += [cfg.unmet_penalty * v for v in u]
    solver.Minimize(solver.Sum(obj))

    result = solver.Solve()
    status_map = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }
    status = status_map.get(result, "UNKNOWN")
    if status not in ("OPTIMAL", "FEASIBLE"):
        return {"solver_status": status, "allocations": [], "total_relocated": 0,
                "unallocated_population": int(sum(h["demand"] for h in sources)),
                "unmet_by_source": [], "site_utilization": [], "objective_value": 0.0,
                "constraint_summary": ["solver did not return a usable solution"],
                "sources": len(sources), "sinks": len(sinks)}

    allocations, used = [], {}
    for (i, j), var in x.items():
        v = int(round(var.solution_value()))
        if v <= 0:
            continue
        allocations.append({
            "source_id": sources[i]["id"], "source_name": sources[i]["name"],
            "site_id": sinks[j]["candidate_id"],
            "population": v,
            "distance_km": round(dist[i][j], 2),
            "site_suitability": float(sinks[j]["suitability_score"]),
        })
        used[j] = used.get(j, 0) + v
    allocations.sort(key=lambda a: -a["population"])

    unmet = int(sum(round(v.solution_value()) for v in u))
    total = int(sum(a["population"] for a in allocations))

    utilisation = [{
        "site_id": sinks[j]["candidate_id"],
        "allocated": used[j],
        "available_capacity": int(sinks[j]["available_capacity"]),
        "utilisation_percent": round(100 * used[j] / max(int(sinks[j]["available_capacity"]), 1), 1),
    } for j in sorted(used, key=lambda k: -used[k])]

    unmet_by_source = [
        {"source_id": sources[i]["id"], "source_name": sources[i]["name"],
         "unallocated": int(round(u[i].solution_value()))}
        for i in range(len(sources)) if round(u[i].solution_value()) > 0
    ]

    summary = [
        f"demand satisfied for {len(sources) - len(unmet_by_source)} of {len(sources)} habitations",
        f"capacity respected at all {len(utilisation)} used sites",
        "safety screen: only sites with status "
        + ("FEASIBLE or REVIEW" if cfg.allow_review_sites else "FEASIBLE")
        + f" were eligible ({len(sinks)} of {len(sites)})",
        f"accessibility screen: destinations beyond {cfg.max_distance_km:.0f} km excluded",
    ]

    return {
        "solver_status": status,
        "objective_value": round(solver.Objective().Value(), 2),
        "allocations": allocations,
        "total_relocated": total,
        "unallocated_population": unmet,
        "unmet_by_source": unmet_by_source,
        "site_utilization": utilisation,
        "constraint_summary": summary,
        "sources": len(sources),
        "sinks": len(sinks),
        "config": {
            "max_distance_km": cfg.max_distance_km,
            "w_distance": cfg.w_distance,
            "w_suitability": cfg.w_suitability,
            "unmet_penalty": cfg.unmet_penalty,
            "allow_review_sites": cfg.allow_review_sites,
            "solver": cfg.solver_name,
        },
    }
