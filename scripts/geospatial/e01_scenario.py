"""Exercise scenario propagation and write the baseline bundle."""
import json, sys, time
import geopandas as gpd
sys.path.insert(0, ".")
from services.scenario_engine import ScenarioParameters, run_scenario

hab = gpd.read_file("data/processed/habitation_risk.geojson")
# allocation.tif indexes settlements by alloc_index, so the list handed to the
# scenario engine must be in that order — habitation_risk.geojson is sorted by
# priority, which is a different order entirely.
hab = hab.sort_values("alloc_index").reset_index(drop=True)
cand = gpd.read_file("data/processed/candidate_capacity.geojson")

habs = [{"id": f"osm-{int(r.osm_id)}", "name": r["name"], "place": r["place"],
         "lon": r.geometry.centroid.x, "lat": r.geometry.centroid.y,
         "site_slope_mean_deg": r.site_slope_mean_deg,
         "dist_to_road_m": r.dist_to_road_m,
         "dist_to_major_road_m": r.dist_to_major_road_m,
         "dist_to_health_m": r.dist_to_health_m,
         "footprint_source": r.footprint_source,
         "analysed_area_km2": r.analysed_area_km2} for _, r in hab.iterrows()]
cands = [{"candidate_id": r.candidate_id, "lon": float(r.lon), "lat": float(r.lat),
          "terrain_score": float(r.terrain_score),
          "road_access_score": float(r.road_access_score),
          "healthcare_access_score": float(r.healthcare_access_score),
          "cap_land": int(r.cap_land), "cap_infrastructure": int(r.cap_infrastructure),
          "cap_healthcare": int(r.cap_healthcare),
          "cap_environmental": int(r.cap_environmental),
          "cap_accessibility": int(r.cap_accessibility),
          "current_population": int(r.current_population)} for _, r in cand.iterrows()]

for label, p in [
    ("BASELINE", ScenarioParameters(0, 0, 100)),
    ("rainfall +25%", ScenarioParameters(25, 0, 100)),
    ("rainfall +25%, pop +10%, roads 85%", ScenarioParameters(25, 10, 85)),
    ("rainfall +50%, roads 60%", ScenarioParameters(50, 0, 60)),
]:
    t0 = time.perf_counter()
    r = run_scenario(p, habs, cands)
    ms = (time.perf_counter() - t0) * 1000
    lv = r["levels"]
    o = r["optimization"]
    print(f"\n=== {label}  ({ms:.0f} ms) ===")
    print(f"  critical {lv.get('critical',0):>4}  high {lv.get('high',0):>4}  "
          f"monitor {lv.get('monitor',0):>4}  safe {lv.get('safe',0):>4}")
    print(f"  settlement exposed population {r['settlement_exposed_population']:>7,}")
    print(f"  feasible sites {r['feasible_sites']:>4}   available capacity {r['total_available_capacity']:>9,}")
    print(f"  solver {o['solver_status']:<10} relocated {o['total_relocated']:>6,}  "
          f"unallocated {o['unallocated_population']:>6,}")
    print(f"  top priority: {r['habitations'][0]['name']} "
          f"(risk {r['habitations'][0]['risk_score']}, {r['habitations'][0]['level']})")
    if label == "BASELINE":
        json.dump(r, open("data/processed/scenario_baseline.json", "w"), indent=1)
