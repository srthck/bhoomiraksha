"""Run the constrained allocation over the real habitations and candidate sites."""
import json
import sys

import geopandas as gpd

sys.path.insert(0, ".")
from services.optimization_engine import OptimizationConfig, solve_allocation  # noqa: E402

hab = gpd.read_file("data/processed/habitation_risk.geojson")
cand = gpd.read_file("data/processed/candidate_capacity.geojson")

# Relocation demand = people standing in High/Very High susceptibility terrain,
# for settlements the risk engine classed critical or high.
need = hab[hab["level"].isin(["critical", "high"]) & (hab["exposed_population"] > 0)]
sources = [{"id": f"osm-{int(r.osm_id)}", "name": r["name"],
            "lon": r.geometry.centroid.x, "lat": r.geometry.centroid.y,
            "demand": int(r.exposed_population)} for _, r in need.iterrows()]
sites = [{"candidate_id": r.candidate_id, "lon": float(r.lon), "lat": float(r.lat),
          "available_capacity": int(r.available_capacity),
          "suitability_score": float(r.suitability_score),
          "screening_status": r.screening_status} for _, r in cand.iterrows()]

print(f"sources (critical/high with exposed people): {len(sources)}, "
      f"total demand {sum(s['demand'] for s in sources):,}")
print(f"candidate sites offered: {len(sites)}")

res = solve_allocation(sources, sites, OptimizationConfig())
json.dump(res, open("data/processed/optimization_baseline.json", "w"), indent=1)

print(f"\nsolver status      {res['solver_status']}")
print(f"objective value    {res['objective_value']:,}")
print(f"eligible sinks     {res['sinks']}")
print(f"total relocated    {res['total_relocated']:,}")
print(f"unallocated        {res['unallocated_population']:,}")
print("\nconstraints:")
for c in res["constraint_summary"]:
    print(f"  - {c}")
print(f"\nallocations: {len(res['allocations'])} (top 10)")
for a in res["allocations"][:10]:
    print(f"  {a['source_name']:22s} -> {a['site_id']}  {a['population']:>5,} people  "
          f"{a['distance_km']:5.1f} km  suitability {a['site_suitability']:.0f}")
if res["unmet_by_source"]:
    print(f"\nunmet demand at {len(res['unmet_by_source'])} habitations:")
    for m in res["unmet_by_source"][:5]:
        print(f"  {m['source_name']}: {m['unallocated']:,}")
print("\nwrote data/processed/optimization_baseline.json")
