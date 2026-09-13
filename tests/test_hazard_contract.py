"""The risk number must always say what hazard it is a risk of.

Also guards the arithmetic the WHY panel displays: component x weight must sum
to the stored risk score, and adding hazard metadata must not move any score.
"""
import sys

import geopandas as gpd
from fastapi.testclient import TestClient

sys.path.insert(0, ".")
from apps.api.main import app  # noqa: E402


def test_detail_names_hazard_and_decomposes_exactly():
    with TestClient(app) as c:
        stored = gpd.read_file("data/processed/habitation_risk.geojson")
        for osm_id in stored.nsmallest(5, "priority_rank")["osm_id"]:
            d = c.get(f"/api/habitations/osm-{int(osm_id)}").json()
            assert d["hazard_type"] == "landslide"
            m = d["hazard_model"]
            assert m["index_label"] == "Landslide risk index"
            assert "probab" in m["meaning"].lower()           # says it is NOT a probability
            assert abs(sum(b["weight"] for b in m["basis"]) - 1.0) < 1e-9
            parts = d["explanation"]["contributions"]
            assert {p["id"] for p in parts} == {"hazard", "exposure", "vulnerability", "response"}
            assert abs(sum(p["contribution"] for p in parts) - d["risk_score"]) <= 0.15
            for p in parts:
                assert abs(p["component_score"] * p["weight"] - p["contribution"]) <= 0.06
            row = stored[stored.osm_id == osm_id].iloc[0]
            assert abs(d["risk_score"] - row.risk_score) < 1e-9, "hazard metadata moved a score"
            assert d["risk_display"] == int(d["risk_score"] + 0.5)
        print("OK: top-5 settlements name their hazard and decompose exactly")


def test_no_unimplemented_hazard_is_served():
    with TestClient(app) as c:
        r = c.get("/api/region").json()
        assert r["hazard_type"] == "landslide"
        text = str(r).lower()
        assert "earthquake risk" not in text and "flood risk" not in text
        print("OK: only the landslide model is served")


if __name__ == "__main__":
    test_detail_names_hazard_and_decomposes_exactly()
    test_no_unimplemented_hazard_is_served()
