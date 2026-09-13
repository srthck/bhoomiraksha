"""Run the risk engine over every settlement and emit the analytical outputs.

Outputs:
  data/processed/habitation_risk.geojson  full geometry + scores + explanation
  data/processed/habitation_risk.json     compact records for the API / UI
"""
import json
import sys

import geopandas as gpd

sys.path.insert(0, ".")
from services.risk_engine import classify, explain, score_habitation  # noqa: E402
from services.risk_engine.explanation import method_note  # noqa: E402

hab = gpd.read_file("data/processed/habitations.geojson")
print(f"scoring {len(hab)} settlements")

records, rows = [], []
for _, row in hab.iterrows():
    rec = {k: (None if gpd.pd.isna(v) else v) for k, v in row.drop("geometry").items()}
    scored = score_habitation(rec)
    level = classify(scored["risk_score"])
    factors = explain(rec, scored)

    rows.append({**scored, "level": level})
    records.append({
        "id": f"osm-{int(rec['osm_id'])}",
        "name": rec["name"],
        "place": rec["place"],
        "lon": round(row.geometry.centroid.x, 5),
        "lat": round(row.geometry.centroid.y, 5),
        "population": int(rec["population"] or 0),
        "exposed_population": int(rec["exposed_population"] or 0),
        "exposed_area_percent": rec["exposed_area_percent"],
        "mean_hazard": rec["mean_hazard"],
        "max_hazard": rec["max_hazard"],
        "site_slope_mean_deg": rec["site_slope_mean_deg"],
        "dist_to_major_road_m": rec["dist_to_major_road_m"],
        "dist_to_health_m": rec["dist_to_health_m"],
        "footprint_source": rec["footprint_source"],
        "risk_score": scored["risk_score"],
        "level": level,
        "components": scored["components"],
        "contributions": scored["contributions"],
        "confidence": scored["confidence"],
        "caveats": scored["caveats"],
        "factors": factors,
    })

hab["risk_score"] = [r["risk_score"] for r in rows]
hab["level"] = [r["level"] for r in rows]
hab["confidence"] = [r["confidence"] for r in rows]
for comp in ("hazard", "exposure", "vulnerability", "response"):
    hab[f"c_{comp}"] = [r["components"][comp] for r in rows]

hab.to_file("data/processed/habitation_risk.geojson", driver="GeoJSON")
records.sort(key=lambda r: -r["risk_score"])
json.dump({
    "region": {
        "name": "Kangra district",
        "code": "HP-KAN",
        "state": "Himachal Pradesh",
        "settlements": len(records),
        "population": int(hab["population"].sum()),
        "exposed_population": int(hab["exposed_population"].sum()),
    },
    "method": method_note(),
    "validated": False,
    "habitations": records,
}, open("data/processed/habitation_risk.json", "w"), indent=1)

# ---- report -------------------------------------------------------------------
counts = hab["level"].value_counts()
print("\nrisk classification:")
for lvl in ("critical", "high", "monitor", "safe"):
    n = int(counts.get(lvl, 0))
    pop = int(hab.loc[hab["level"] == lvl, "population"].sum())
    print(f"  {lvl:9s} {n:>5} settlements   {pop:>9,} residents")

print(f"\ndistrict totals: {int(hab['population'].sum()):,} residents in settlements, "
      f"{int(hab['exposed_population'].sum()):,} in High/Very High terrain")

print("\ntop 12 by risk score:")
cols = ["name", "place", "risk_score", "level", "population", "exposed_population",
        "exposed_area_percent", "mean_hazard"]
print(hab.nlargest(12, "risk_score")[cols].to_string(index=False))

# ---- Milestone 1 card ---------------------------------------------------------
top = records[0]
print("\n" + "=" * 62)
print(f"  MILESTONE 1 — {top['name'].upper()} ({top['place']})")
print("=" * 62)
print(f"  Hazard susceptibility        {top['mean_hazard']:.1f}")
print(f"  Exposed area                 {top['exposed_area_percent']:.1f} %")
print(f"  Population                   {top['population']:,}")
print(f"  Estimated exposed population {top['exposed_population']:,}")
print(f"  Site slope                   {top['site_slope_mean_deg']:.0f} deg")
print(f"  Distance to major road       {top['dist_to_major_road_m'] / 1000:.1f} km")
print(f"  Distance to health care      {top['dist_to_health_m'] / 1000:.1f} km")
print()
print(f"  Risk score                   {top['risk_score']}")
print(f"  Classification               {top['level'].upper()}")
print(f"  Confidence                   {top['confidence']}")
print("\n  WHY?")
for f in top["factors"]:
    print(f"    {f['label']:24s} +{f['contribution']:5.1f}")
print(f"    {'':24s} ------")
print(f"    {'Risk score':24s}  {top['risk_score']:5.1f}")
print("\n  Caveats:")
for c in top["caveats"]:
    print(f"    - {c}")
print("=" * 62)
print("\nwrote habitation_risk.geojson and habitation_risk.json")
