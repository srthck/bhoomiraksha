"""Cross-endpoint consistency: the same entity must carry the same numbers
at every stage of the decision loop.

Requires the API on :8000.
"""
import json
import urllib.request

B = "http://localhost:8000"


def get(p):
    return json.load(urllib.request.urlopen(B + p, timeout=120))


def post(p, body):
    r = urllib.request.Request(B + p, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=300))


def test_decision_loop_is_consistent():
    top = get("/api/priority?limit=1")[0]
    hid = top["id"]
    reg = get("/api/region")
    hab = get(f"/api/habitations/{hid}")
    exp = get(f"/api/exposure/{hid}")
    site = get(f"/api/relocation/sites?habitation_id={hid}&limit=1")[0]
    cap = get(f"/api/capacity/{site['candidate_id']}?habitation_id={hid}")
    opt = post("/api/optimization/run", {"habitation_ids": [hid], "max_distance_km": 40})
    brief = get(f"/api/executive-brief/{hid}")

    assert exp["exposed_population"] == hab["exposed_population"]
    assert brief["habitation"]["risk_score"] == hab["risk_score"]
    assert brief["recommended"]["relocation_demand"] == hab["exposed_population"]
    assert opt["total_relocated"] + opt["unallocated_population"] == hab["exposed_population"]
    assert cap["available_capacity"] == site["available_capacity"]
    assert brief["recommended"]["preferred_site"] == site["candidate_id"]
    assert abs(sum(hab["contributions"].values()) - hab["risk_score"]) < 0.11
    assert reg["settlement_exposed_population"] < reg["district_exposed_population"]
    assert hab["explanation"]["method"] == "Transparent Weighted Contribution"
    assert "shap" not in json.dumps(hab).lower().replace("not shap", "")
    assert opt["solver_status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "NO_DEMAND")
    print(f"OK: {hab['name']} consistent across exposure, risk, capacity, "
          f"optimisation and brief")


def test_zero_delta_scenario_shows_no_change():
    d = post("/api/scenario/run", {"rainfall_delta_percent": 0,
                                   "population_delta_percent": 0,
                                   "road_availability_percent": 100})
    moved = [x["label"] for x in d["deltas"] if abs(x["delta"]) > 0.001]
    assert not moved, f"zero-delta scenario reported changes in {moved}"
    assert not d["changed_habitations"]
    print("OK: zero-delta scenario is a no-op on every metric")


def test_scenario_propagates_and_reports_solver_truthfully():
    d = post("/api/scenario/run", {"rainfall_delta_percent": 50,
                                   "population_delta_percent": 0,
                                   "road_availability_percent": 60})
    by = {x["label"]: x for x in d["deltas"]}
    assert by["Exposed population"]["delta"] > 0
    assert by["Feasible relocation sites"]["delta"] < 0
    assert d["changed_habitations"]
    assert d["optimization"]["solver_status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE")
    print(f"OK: rainfall +50%/roads 60% -> exposure "
          f"{by['Exposed population']['baseline']:,.0f} to {by['Exposed population']['scenario']:,.0f}, "
          f"{len(d['changed_habitations'])} reclassified, solver {d['optimization']['solver_status']}")


if __name__ == "__main__":
    test_decision_loop_is_consistent()
    test_zero_delta_scenario_shows_no_change()
    test_scenario_propagates_and_reports_solver_truthfully()
