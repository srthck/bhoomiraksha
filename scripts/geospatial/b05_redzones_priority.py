"""Red zones (Phase 7) and relocation priority (Phase 8).

RED ZONES
    Previously the UI drew a red circle wherever a record said level ===
    'critical'. Here the red zone is real geometry: the susceptibility surface
    is thresholded at the High break (>= 60), polygonised, and cleaned. The map
    renders an analytical result rather than a decoration.

PRIORITY
    Risk answers "how dangerous is this place". Priority answers "where should
    the authority act first", which is a different question — a hamlet of 14
    entirely inside hazardous ground can be the highest-risk settlement in the
    district while a larger exposed town is the more urgent intervention.

    priority = 0.45 * risk
             + 0.35 * exposed_population (log-scaled)
             + 0.20 * response_difficulty

    Weights are documented judgement. The rationale: risk still leads, but the
    number of people actually exposed is what converts danger into caseload,
    and difficulty of reach is what converts caseload into lead time.
"""
import json
import sys

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

sys.path.insert(0, ".")
from services.risk_engine.normalization import log_scale  # noqa: E402

HIGH_BREAK = 60.0
MIN_ZONE_KM2 = 0.05      # drop specks below ~5 ha; they are raster noise
SIMPLIFY_M = 30.0        # one cell; keeps shape, cuts vertex count for the web

# ---- red zones ----------------------------------------------------------------
with rasterio.open("data/processed/landslide_susceptibility.tif") as src:
    susc = src.read(1)
    transform, crs = src.transform, src.crs

mask = np.isfinite(susc) & (susc >= HIGH_BREAK)
print(f"cells at or above the High break: {int(mask.sum()):,}")

geoms, values = [], []
for geom, val in shapes(mask.astype(np.uint8), mask=mask, transform=transform):
    geoms.append(shape(geom))
    values.append(val)

zones = gpd.GeoDataFrame({"value": values}, geometry=geoms, crs=crs)
zones["area_km2"] = zones.geometry.area / 1e6
before = len(zones)
zones = zones[zones["area_km2"] >= MIN_ZONE_KM2].copy()
zones["geometry"] = zones.geometry.simplify(SIMPLIFY_M, preserve_topology=True)

# attach the mean susceptibility of each polygon so the UI can shade them
from rasterio.features import rasterize  # noqa: E402

zid = rasterize(((g, i + 1) for i, g in enumerate(zones.geometry)),
                out_shape=susc.shape, transform=transform, fill=0, dtype="int32")
flat, sv = zid.ravel(), susc.ravel()
sel = (flat > 0) & np.isfinite(sv)
ids = flat[sel] - 1
cnt = np.bincount(ids, minlength=len(zones))
tot = np.bincount(ids, weights=sv[sel], minlength=len(zones))
zones["mean_susceptibility"] = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan).round(1)
zones["severity"] = np.where(zones["mean_susceptibility"] >= 80, "very_high", "high")

zones[["area_km2", "mean_susceptibility", "severity", "geometry"]].to_crs("EPSG:4326") \
    .to_file("data/processed/red_zones.geojson", driver="GeoJSON")

print(f"red zones: {before} raw polygons -> {len(zones)} kept "
      f"(>= {MIN_ZONE_KM2} km2), {zones['area_km2'].sum():,.0f} km2 total")
print(zones["severity"].value_counts().to_string())
print(f"largest contiguous zone: {zones['area_km2'].max():,.1f} km2")

# ---- priority -----------------------------------------------------------------
hab = gpd.read_file("data/processed/habitation_risk.geojson")

risk_term = hab["risk_score"].fillna(0)
people_term = hab["exposed_population"].fillna(0).apply(lambda v: log_scale(v, 5000.0))
response_term = hab["c_response"].fillna(0)

hab["priority_score"] = (0.45 * risk_term + 0.35 * people_term + 0.20 * response_term).round(1)
hab = hab.sort_values("priority_score", ascending=False).reset_index(drop=True)
hab["priority_rank"] = np.arange(1, len(hab) + 1)

hab.to_file("data/processed/habitation_risk.geojson", driver="GeoJSON")

# refresh the compact JSON with priority attached
payload = json.load(open("data/processed/habitation_risk.json"))
by_id = {f"osm-{int(r['osm_id'])}": (float(r["priority_score"]), int(r["priority_rank"]))
         for _, r in hab.iterrows()}
for rec in payload["habitations"]:
    if rec["id"] in by_id:
        rec["priority_score"], rec["priority_rank"] = by_id[rec["id"]]
payload["habitations"].sort(key=lambda r: r.get("priority_rank", 10**6))
payload["priority_formula"] = ("0.45*risk + 0.35*log(exposed_population) + "
                               "0.20*response_difficulty; uncalibrated judgement weights")
json.dump(payload, open("data/processed/habitation_risk.json", "w"), indent=1)

cols = ["priority_rank", "name", "place", "risk_score", "level",
        "population", "exposed_population", "priority_score"]
print("\nrelocation priority, top 12:")
print(hab.head(12)[cols].to_string(index=False))
print("\nwrote red_zones.geojson; priority added to habitation_risk.*")
