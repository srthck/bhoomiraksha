"""The scenario engine at zero-delta must reproduce the stored pipeline exactly.

If these drift apart the UI will show one set of numbers on the map and a
different set in the scenario panel, which is the specific failure the demo
cannot afford.
"""
import sys
import geopandas as gpd
sys.path.insert(0, ".")
from services.scenario_engine import ScenarioParameters, run_scenario


def _load():
    hab = gpd.read_file("data/processed/habitation_risk.geojson").sort_values("alloc_index").reset_index(drop=True)
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
    return hab, habs, cands


def test_zero_delta_scenario_matches_pipeline():
    hab, habs, cands = _load()
    r = run_scenario(ScenarioParameters(0, 0, 100), habs, cands)
    by_id = {x["id"]: x for x in r["habitations"]}

    mismatches = []
    for _, row in hab.iterrows():
        s = by_id[f"osm-{int(row.osm_id)}"]
        for field, stored in (("risk_score", row.risk_score),
                              ("mean_hazard", row.mean_hazard),
                              ("exposed_population", row.exposed_population),
                              ("population", row.population)):
            if abs(float(s[field]) - float(stored)) > 0.15:
                mismatches.append(f"{row['name']}.{field}: {s[field]} vs {stored}")
    assert not mismatches, "scenario baseline drifted from pipeline:\n" + "\n".join(mismatches[:10])

    counts = r["levels"]
    stored_counts = hab["level"].value_counts().to_dict()
    assert counts == stored_counts, f"level counts differ: {counts} vs {stored_counts}"
    print(f"OK: {len(hab)} settlements identical; levels {counts}")


def test_scenario_actually_propagates():
    _, habs, cands = _load()
    base = run_scenario(ScenarioParameters(0, 0, 100), habs, cands)
    wet = run_scenario(ScenarioParameters(40, 0, 100), habs, cands)
    assert wet["settlement_exposed_population"] > base["settlement_exposed_population"], \
        "more rainfall must not reduce exposure"
    assert wet["feasible_sites"] <= base["feasible_sites"], \
        "more rainfall must not create safer candidate sites"
    print(f"OK: rainfall +40% moved exposure {base['settlement_exposed_population']:,}"
          f" -> {wet['settlement_exposed_population']:,}, "
          f"feasible sites {base['feasible_sites']} -> {wet['feasible_sites']}")


if __name__ == "__main__":
    test_zero_delta_scenario_matches_pipeline()
    test_scenario_actually_propagates()
