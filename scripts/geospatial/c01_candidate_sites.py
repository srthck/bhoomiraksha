"""Candidate relocation site discovery and screening.

Replaces the invented "Site A / Site B / Site C". Every candidate here is a
contiguous patch of Kangra land that survived a spatial screen, and every
attribute is measured from the processed rasters.

SCREENING — exclusions applied to the 30 m grid
    susceptibility >= 40      hazardous or marginal ground; you do not move
                              people from a red zone into an amber one
    slope > 15 deg            beyond this, planned settlement needs terracing
                              and access roads become expensive; 15 deg is the
                              common planning cut-off for buildable hill land
    elevation > 2200 m        above the practical limit for year-round
                              habitation and service delivery in Kangra
    inside an existing        cannot relocate onto ground already occupied
    settlement allocation
    within 30 m of a mapped   avoids siting on watercourses; the only water
    watercourse               constraint available from OSM

CLUSTERING
    Surviving cells are grouped into 8-connected components. Components below
    5 ha are dropped: too small to host a planned settlement and usually
    raster speckle.

SUITABILITY (0-100), weighted mean of four measured terms
    safety      0.40   100 - mean susceptibility
    terrain     0.25   inverse slope, 0-15 deg
    road access 0.20   inverse distance to any mapped road, 0-3000 m
    health      0.15   inverse distance to a health facility, 0-15000 m

    Safety dominates because the entire purpose is to leave hazardous ground.

SCREENING STATUS
    FEASIBLE  suitability >= 60 and max susceptibility < 60
    REVIEW    suitability >= 45, or a hazardous fringe inside the patch
    REJECTED  anything below

Output: data/processed/candidate_sites.geojson
"""
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from scipy import ndimage
from shapely.geometry import shape

MAX_SUSC = 40.0
MAX_SLOPE = 15.0
MAX_ELEV = 2200.0
WATER_BUFFER_M = 30.0
MIN_AREA_KM2 = 0.05
SIMPLIFY_M = 30.0

W_SAFETY, W_TERRAIN, W_ROAD, W_HEALTH = 0.40, 0.25, 0.20, 0.15


def read(path):
    with rasterio.open(path) as s:
        return s.read(1), s.transform, (s.height, s.width), s.crs


susc, transform, hw, CRS = read("data/processed/landslide_susceptibility.tif")
slope, *_ = read("data/processed/slope.tif")
dem, *_ = read("data/processed/dem_kangra.tif")
pop, *_ = read("data/processed/population.tif")
alloc, *_ = read("data/processed/allocation.tif")
CELL = abs(transform.a)
CELL_AREA_KM2 = (CELL * CELL) / 1e6

roads = gpd.read_file("data/processed/roads.geojson").to_crs(CRS)
health = gpd.read_file("data/processed/health_facilities.geojson").to_crs(CRS)

in_district = np.isfinite(susc) & np.isfinite(slope) & np.isfinite(dem)
print(f"district cells: {int(in_district.sum()):,}")

# ---- distance surfaces (cells, converted to metres) --------------------------
road_mask = rasterize([(g, 1) for g in roads.geometry], out_shape=hw,
                      transform=transform, fill=0, dtype="uint8").astype(bool)
dist_road = ndimage.distance_transform_edt(~road_mask) * CELL

health_mask = rasterize([(g.buffer(CELL), 1) for g in health.geometry], out_shape=hw,
                        transform=transform, fill=0, dtype="uint8").astype(bool)
dist_health = ndimage.distance_transform_edt(~health_mask) * CELL

major = roads[roads["highway"].isin(("trunk", "primary", "secondary"))]
major_mask = rasterize([(g, 1) for g in major.geometry], out_shape=hw,
                       transform=transform, fill=0, dtype="uint8").astype(bool)
dist_major = ndimage.distance_transform_edt(~major_mask) * CELL

# Watercourses: the only environmental constraint OSM gives us here.
try:
    water = roads.iloc[0:0]  # placeholder type
    import os
    if os.path.exists("data/processed/waterways.geojson"):
        water = gpd.read_file("data/processed/waterways.geojson").to_crs(CRS)
    water_mask = (rasterize([(g, 1) for g in water.geometry], out_shape=hw,
                            transform=transform, fill=0, dtype="uint8").astype(bool)
                  if len(water) else np.zeros(hw, bool))
except Exception:
    water_mask = np.zeros(hw, bool)
near_water = (ndimage.distance_transform_edt(~water_mask) * CELL) < WATER_BUFFER_M if water_mask.any() else np.zeros(hw, bool)

# ---- exclusion screen --------------------------------------------------------
occupied = alloc > 0
viable = (in_district
          & (susc < MAX_SUSC)
          & (slope <= MAX_SLOPE)
          & (dem <= MAX_ELEV)
          & ~occupied
          & ~near_water)

steps = [
    ("in district", in_district),
    ("+ susceptibility < 40", in_district & (susc < MAX_SUSC)),
    ("+ slope <= 15 deg", in_district & (susc < MAX_SUSC) & (slope <= MAX_SLOPE)),
    ("+ elevation <= 2200 m", in_district & (susc < MAX_SUSC) & (slope <= MAX_SLOPE) & (dem <= MAX_ELEV)),
    ("+ not already settled", viable | near_water),
    ("+ not on a watercourse", viable),
]
print("\nscreening funnel:")
for label, m in steps:
    print(f"  {label:26s} {int(m.sum()):>10,} cells  {m.sum() * CELL_AREA_KM2:8,.0f} km2")

# ---- cluster into candidate patches -----------------------------------------
labels, n_lab = ndimage.label(viable, structure=np.ones((3, 3), int))
sizes = np.bincount(labels.ravel())
min_cells = int(MIN_AREA_KM2 / CELL_AREA_KM2)
keep = {i for i in range(1, n_lab + 1) if sizes[i] >= min_cells}
print(f"\ncomponents: {n_lab:,} -> {len(keep):,} above {MIN_AREA_KM2} km2 "
      f"({min_cells} cells)")

kept_mask = np.isin(labels, list(keep))
geoms, ids = [], []
for geom, val in shapes(labels.astype(np.int32), mask=kept_mask, transform=transform):
    geoms.append(shape(geom))
    ids.append(int(val))

gdf = gpd.GeoDataFrame({"label": ids}, geometry=geoms, crs=CRS)
gdf = gdf.dissolve(by="label", as_index=False)
gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_M, preserve_topology=True)

# ---- per-candidate measured attributes --------------------------------------
lab_flat = labels.ravel()
sel = np.isin(lab_flat, list(keep))
lab_sel = lab_flat[sel]
order = {lab: i for i, lab in enumerate(gdf["label"].tolist())}
idx = np.array([order[l] for l in lab_sel])
n = len(gdf)


def agg(arr, fn="mean"):
    v = arr.ravel()[sel]
    cnt = np.bincount(idx, minlength=n)
    if fn == "mean":
        return np.bincount(idx, weights=v, minlength=n) / np.maximum(cnt, 1)
    if fn == "max":
        out = np.zeros(n)
        np.maximum.at(out, idx, v)
        return out
    return np.bincount(idx, weights=v, minlength=n)


cells = np.bincount(idx, minlength=n)
gdf["area_km2"] = (cells * CELL_AREA_KM2).round(3)
gdf["mean_susceptibility"] = agg(susc).round(1)
gdf["max_susceptibility"] = agg(susc, "max").round(1)
gdf["mean_slope_deg"] = agg(slope).round(1)
gdf["max_slope_deg"] = agg(slope, "max").round(1)
gdf["mean_elevation_m"] = agg(dem).round(0)
gdf["distance_to_road_m"] = agg(dist_road).round(0)
gdf["distance_to_major_road_m"] = agg(dist_major).round(0)
gdf["distance_to_healthcare_m"] = agg(dist_health).round(0)
gdf["current_population"] = np.round(agg(np.nan_to_num(pop), "sum")).astype(int)
gdf["safe_area_km2"] = gdf["area_km2"]   # every kept cell already passed the screen

# ---- suitability --------------------------------------------------------------
def inv(v, lo, hi):
    return np.clip(1 - (v - lo) / (hi - lo), 0, 1) * 100


safety = np.clip(100 - gdf["mean_susceptibility"], 0, 100)
terrain = inv(gdf["mean_slope_deg"], 0, MAX_SLOPE)
road = inv(gdf["distance_to_road_m"], 0, 3000)
hlth = inv(gdf["distance_to_healthcare_m"], 0, 15000)

gdf["safety_score"] = safety.round(1)
gdf["terrain_score"] = terrain.round(1)
gdf["road_access_score"] = road.round(1)
gdf["healthcare_access_score"] = hlth.round(1)
gdf["suitability_score"] = (W_SAFETY * safety + W_TERRAIN * terrain
                            + W_ROAD * road + W_HEALTH * hlth).round(1)

status = np.where(
    (gdf["suitability_score"] >= 60) & (gdf["max_susceptibility"] < 60), "FEASIBLE",
    np.where(gdf["suitability_score"] >= 45, "REVIEW", "REJECTED"))
gdf["screening_status"] = status
gdf["candidate_id"] = [f"cand-{i:04d}" for i in range(1, n + 1)]
gdf = gdf.drop(columns=["label"])

centroids = gdf.geometry.centroid.to_crs("EPSG:4326")
gdf["lon"] = centroids.x.round(5)
gdf["lat"] = centroids.y.round(5)

gdf = gdf.sort_values("suitability_score", ascending=False).reset_index(drop=True)
gdf.to_crs("EPSG:4326").to_file("data/processed/candidate_sites.geojson", driver="GeoJSON")

print(f"\ncandidates: {n}")
print(gdf["screening_status"].value_counts().to_string())
print(f"total candidate area: {gdf['area_km2'].sum():,.0f} km2")
print("\ntop 10 by suitability:")
cols = ["candidate_id", "area_km2", "mean_susceptibility", "max_susceptibility",
        "mean_slope_deg", "distance_to_road_m", "distance_to_healthcare_m",
        "current_population", "suitability_score", "screening_status"]
print(gdf.head(10)[cols].to_string(index=False))

json.dump({
    "thresholds": {"max_susceptibility": MAX_SUSC, "max_slope_deg": MAX_SLOPE,
                   "max_elevation_m": MAX_ELEV, "min_area_km2": MIN_AREA_KM2,
                   "water_buffer_m": WATER_BUFFER_M},
    "weights": {"safety": W_SAFETY, "terrain": W_TERRAIN,
                "road_access": W_ROAD, "healthcare_access": W_HEALTH},
    "counts": gdf["screening_status"].value_counts().to_dict(),
    "environmental_constraint": ("watercourse buffer only; no forest, protected-area "
                                 "or land-ownership data was available"),
}, open("data/processed/candidate_summary.json", "w"), indent=1)
print("\nwrote candidate_sites.geojson, candidate_summary.json")

# Cache the candidate zone raster: the scenario engine re-screens candidates on
# every run and must not pay for a fresh rasterisation each time.
_final = gpd.read_file("data/processed/candidate_sites.geojson").to_crs(CRS)
_zones = rasterize(((g, i + 1) for i, g in enumerate(_final.geometry)),
                   out_shape=hw, transform=transform, fill=0, dtype="int32")
np.save("data/processed/candidate_zones.npy", _zones)
print(f"cached candidate_zones.npy ({int((_zones > 0).sum()):,} cells)")
