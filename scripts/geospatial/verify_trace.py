"""Traceability check: re-derive one settlement's numbers from the rasters.

Milestone 1 requires that every displayed number can be traced back to an input
and a calculation. This reads the source rasters directly and recomputes the
stored values independently of the pipeline that produced them.
"""
import json
import sys

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

sys.path.insert(0, ".")
from services.risk_engine import classify, explain, score_habitation  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "Upper Bara Bhanghal"
hab = gpd.read_file("data/processed/habitation_risk.geojson")
row = hab[hab["name"] == NAME].iloc[0]
print(f"TRACE: {NAME} ({row['place']})  priority rank #{int(row['priority_rank'])}\n")

with rasterio.open("data/processed/landslide_susceptibility.tif") as s:
    susc, transform, hw = s.read(1), s.transform, (s.height, s.width)
with rasterio.open("data/processed/population.tif") as s:
    pop = s.read(1)
with rasterio.open("data/processed/slope.tif") as s:
    slope = s.read(1)

geom = gpd.GeoSeries([row.geometry], crs="EPSG:4326").to_crs("EPSG:32643").iloc[0]
m = rasterize([(geom, 1)], out_shape=hw, transform=transform, fill=0, dtype="uint8").astype(bool)
sel = m & np.isfinite(susc)
sv, pv, slv = susc[sel], np.nan_to_num(pop[sel]), slope[sel]

print(f"  cells in footprint            {sel.sum()}")
checks = [
    ("mean_hazard",           sv.mean(),                              row["mean_hazard"]),
    ("max_hazard",            sv.max(),                               row["max_hazard"]),
    ("exposed_area_percent",  100 * (sv >= 60).mean(),                row["exposed_area_percent"]),
    ("population",            pv.sum(),                               row["population"]),
    ("exposed_population",    pv[sv >= 60].sum(),                     row["exposed_population"]),
    ("site_slope_mean_deg",   np.nanmean(slv),                        row["site_slope_mean_deg"]),
]
print(f"\n  {'field':24s} {'recomputed':>12s} {'stored':>12s}  match")
ok = True
for name, got, stored in checks:
    good = abs(float(got) - float(stored)) <= max(1.0, abs(float(stored)) * 0.01)
    ok &= good
    print(f"  {name:24s} {float(got):12.1f} {float(stored):12.1f}  {'OK' if good else 'MISMATCH'}")

rec = {k: (None if gpd.pd.isna(v) else v) for k, v in row.drop("geometry").items()}
scored = score_habitation(rec)
print(f"\n  risk recomputed {scored['risk_score']} vs stored {row['risk_score']}  "
      f"{'OK' if abs(scored['risk_score'] - row['risk_score']) < 0.1 else 'MISMATCH'}")
print(f"  classification  {classify(scored['risk_score'])}")
print("\n  WHY (contributions sum to the risk score):")
tot = 0.0
for f in explain(rec, scored):
    tot += f["contribution"]
    print(f"    {f['label']:24s} +{f['contribution']:5.1f}   {f['evidence']}")
print(f"    {'':24s} ------")
print(f"    {'total':24s}  {tot:5.1f}")
print(f"\n  RESULT: {'all traceable' if ok else 'DIFFERENCES FOUND'}")
if not ok:
    print("  NOTE: a settlement whose footprint overlaps its neighbours will differ.")
    print("        The pipeline gives each shared cell to exactly one settlement;")
    print("        this script rasterises the settlement on its own.")
    print("        See docs/limitations.md section 4b.")
