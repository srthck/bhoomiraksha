"""Accessibility and site-terrain metrics for every settlement.

These feed the vulnerability and response-difficulty terms of the risk engine.
All four are measured from real data — no scores are assigned by hand.

  site_slope_mean_deg   mean slope inside the settlement footprint. A steeper
                        site means buildings, roads and services sit on ground
                        that is itself less stable.
  dist_to_road_m        straight-line distance to the nearest mapped road of
                        any class. Proxy for everyday access.
  dist_to_major_road_m  distance to the nearest trunk/primary/secondary road.
                        Proxy for whether heavy rescue and evacuation vehicles
                        can reach the settlement.
  dist_to_health_m      distance to the nearest mapped health facility.

HONESTY NOTE
    These are Euclidean distances, not travel times along the network. In
    mountainous terrain the real travel distance can be several times the
    straight line. A road-network routing cost would be better and is recorded
    as future work in docs/limitations.md.

    OSM health-facility coverage in rural Himachal is incomplete, so
    dist_to_health_m is a lower bound on true remoteness in some places.
"""
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

CRS = "EPSG:32643"
MAJOR = ("trunk", "primary", "secondary")

hab = gpd.read_file("data/processed/habitations.geojson").to_crs(CRS)
roads = gpd.read_file("data/processed/roads.geojson").to_crs(CRS)
health = gpd.read_file("data/processed/health_facilities.geojson").to_crs(CRS)
print(f"{len(hab)} settlements, {len(roads)} road segments, {len(health)} health facilities")

# ---- mean slope inside each footprint ---------------------------------------
with rasterio.open("data/processed/slope.tif") as s:
    slope = s.read(1)
    transform, shape_hw = s.transform, (s.height, s.width)

# Use the allocation written by b02 — NOT a fresh rasterisation of the
# footprints, which overlap and would disagree with the exposure numbers.
with rasterio.open("data/processed/allocation.tif") as a:
    zones = a.read(1)
flat, sv = zones.ravel(), slope.ravel()
sel = (flat > 0) & np.isfinite(sv)
ids = flat[sel] - 1
n = len(hab)
cnt = np.bincount(ids, minlength=n)
tot = np.bincount(ids, weights=sv[sel], minlength=n)
hab["site_slope_mean_deg"] = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan).round(1)
print(f"  settlements with no valid slope cell: {int((cnt == 0).sum())}")

# ---- nearest-feature distances ----------------------------------------------
centroids = gpd.GeoDataFrame(geometry=hab.geometry.centroid, crs=CRS)


def nearest_distance(targets, label):
    if len(targets) == 0:
        print(f"  {label}: no features — leaving as NaN")
        return np.full(len(centroids), np.nan)
    joined = gpd.sjoin_nearest(centroids, targets[["geometry"]], how="left",
                               distance_col="_d")
    # sjoin_nearest can emit ties; keep the first per input row
    return joined.groupby(joined.index)["_d"].min().reindex(centroids.index).to_numpy()


hab["dist_to_road_m"] = np.round(nearest_distance(roads, "roads"))
hab["dist_to_major_road_m"] = np.round(
    nearest_distance(roads[roads["highway"].isin(MAJOR)], "major roads"))
hab["dist_to_health_m"] = np.round(nearest_distance(health, "health facilities"))

hab.to_crs("EPSG:4326").to_file("data/processed/habitations.geojson", driver="GeoJSON")

# ---- report -------------------------------------------------------------------
def describe(col, unit):
    v = hab[col].dropna()
    print(f"  {col:24s} median {np.median(v):8,.0f}  p90 {np.percentile(v, 90):8,.0f}  "
          f"max {v.max():8,.0f} {unit}")


print("\nsettlement metrics:")
describe("site_slope_mean_deg", "deg")
describe("dist_to_road_m", "m")
describe("dist_to_major_road_m", "m")
describe("dist_to_health_m", "m")
print(f"\n  settlements >2 km from any road:        {(hab['dist_to_road_m'] > 2000).sum()}")
print(f"  settlements >10 km from a major road:   {(hab['dist_to_major_road_m'] > 10000).sum()}")
print(f"  settlements >10 km from health care:    {(hab['dist_to_health_m'] > 10000).sum()}")
print("\nupdated data/processed/habitations.geojson")
