"""Carrying capacity for every candidate site.

    effective_capacity = MIN(land, infrastructure, healthcare,
                             environmental, accessibility)
    available_capacity = MAX(0, effective_capacity - current_population)
    binding_constraint = whichever constraint produced the minimum

Each constraint is tagged with how it was obtained:

    DERIVED                   computed from measured raster/vector data
    CURATED_PILOT_ASSUMPTION  a documented planning figure standing in for data
                              that was not available. Labelled, never disguised.

--- LAND (DERIVED + one curated density) ------------------------------------
Developable area is measured from the slope raster inside the candidate:
cells at or below 10 deg count fully, cells from 10-15 deg count half (they
need terracing). Gross residential density of 100 persons/hectare for planned
low-rise hill resettlement is a CURATED_PILOT_ASSUMPTION.

--- ENVIRONMENTAL (DERIVED) --------------------------------------------------
The binding environmental resource in a hill settlement is water. Yield is
computed from the actual rainfall raster over the candidate:

    yield_m3_per_year = annual_rainfall_m * area_m2 * runoff_coefficient
    capacity = yield / (55 litres per capita per day * 365)

55 lpcd is the Jal Jeevan Mission rural service norm. The runoff coefficient
of 0.15 (locally capturable share) is a CURATED_PILOT_ASSUMPTION.

--- HEALTHCARE (DERIVED) -----------------------------------------------------
Uses the real OSM facilities within 10 km and Indian public-health service
norms (IPHS, hill-area figures):

    hospital           30,000 persons
    health centre      20,000 persons   (PHC)
    clinic / doctors    3,000 persons   (sub-centre)
    pharmacy, dentist,
    lab, other              0           not primary care

Spare capacity = sum of norms in range minus the population already inside
that same 10 km, so an area whose facilities are already saturated offers no
headroom.

--- INFRASTRUCTURE and ACCESSIBILITY (CURATED ceilings, DERIVED modifiers) ---
No electricity, water-supply or piped-network dataset was available. Both use
a documented ceiling scaled by measured road distance. Labelled accordingly.

Output: data/processed/candidate_capacity.geojson / .json
"""
import json
import os
import zipfile

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject

DENSITY_PER_HA = 100.0        # CURATED_PILOT_ASSUMPTION
RUNOFF_COEFF = 0.15           # CURATED_PILOT_ASSUMPTION
LPCD = 55.0                   # Jal Jeevan Mission rural norm
HEALTH_RADIUS_M = 10000.0
IPHS_NORM = {"hospital": 30000, "centre": 20000, "clinic": 3000, "doctors": 3000}
INFRA_CEILING = 12000.0       # CURATED_PILOT_ASSUMPTION
ACCESS_CEILING = 15000.0      # CURATED_PILOT_ASSUMPTION

# ---- annual rainfall (needed for water yield; a04 only kept the monsoon) -----
ANNUAL = "data/processed/rainfall_annual.tif"
if not os.path.exists(ANNUAL):
    print("building annual rainfall from the cached WorldClim archive…")
    total, src_transform, src_crs = None, None, None
    with zipfile.ZipFile("data/raw/wc2.1_2.5m_prec.zip") as z:
        names = sorted(n for n in z.namelist() if n.endswith(".tif"))
        z.extractall("data/raw/worldclim_prec", members=names)
    d = "data/raw/worldclim_prec"
    for f in sorted(os.listdir(d)):
        if not f.endswith(".tif"):
            continue
        with rasterio.open(os.path.join(d, f)) as s:
            a = s.read(1).astype(np.float32)
            a = np.where(a < 0, np.nan, a)
            total = a if total is None else total + a
            src_transform, src_crs = s.transform, s.crs
    with rasterio.open("data/processed/slope.tif") as ref:
        prof, dst = ref.profile, np.full((ref.height, ref.width), np.nan, np.float32)
        reproject(source=total, destination=dst,
                  src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
                  dst_transform=ref.transform, dst_crs=ref.crs, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
        valid = np.isfinite(ref.read(1))
    with rasterio.open(ANNUAL, "w", **prof) as o:
        o.write(np.where(valid, dst, np.nan).astype(np.float32), 1)
        o.update_tags(source="WorldClim 2.1 2.5 arc-min, 12-month sum", units="mm")

# ---- load ---------------------------------------------------------------------
cand = gpd.read_file("data/processed/candidate_sites.geojson")
with rasterio.open("data/processed/slope.tif") as s:
    slope, transform, hw, CRS = s.read(1), s.transform, (s.height, s.width), s.crs
with rasterio.open(ANNUAL) as s:
    rain_annual = s.read(1)
with rasterio.open("data/processed/population.tif") as s:
    pop = np.nan_to_num(s.read(1))
CELL = abs(transform.a)
CELL_M2 = CELL * CELL

cand_m = cand.to_crs(CRS)
health = gpd.read_file("data/processed/health_facilities.geojson").to_crs(CRS)
n = len(cand_m)

zones = rasterize(((g, i + 1) for i, g in enumerate(cand_m.geometry)),
                  out_shape=hw, transform=transform, fill=0, dtype="int32")
flat = zones.ravel()
sel = flat > 0
idx = flat[sel] - 1
cells = np.bincount(idx, minlength=n)

sl = slope.ravel()[sel]
ra = rain_annual.ravel()[sel]

# ---- LAND ---------------------------------------------------------------------
gentle = np.bincount(idx, weights=(sl <= 10).astype(float), minlength=n)
terraced = np.bincount(idx, weights=((sl > 10) & (sl <= 15)).astype(float), minlength=n)
developable_ha = (gentle + 0.5 * terraced) * CELL_M2 / 10000.0
land_cap = developable_ha * DENSITY_PER_HA

# ---- ENVIRONMENTAL (water yield) ---------------------------------------------
rain_ok = np.isfinite(ra)
rain_sum = np.bincount(idx[rain_ok], weights=ra[rain_ok], minlength=n)
rain_cnt = np.bincount(idx[rain_ok], minlength=n)
mean_rain_mm = np.where(rain_cnt > 0, rain_sum / np.maximum(rain_cnt, 1), 0.0)
area_m2 = cells * CELL_M2
yield_m3 = (mean_rain_mm / 1000.0) * area_m2 * RUNOFF_COEFF
env_cap = yield_m3 / (LPCD / 1000.0 * 365.0)

# ---- HEALTHCARE ----------------------------------------------------------------
norms = health["kind"].map(IPHS_NORM).fillna(0).to_numpy()
hx = health.geometry.x.to_numpy()
hy = health.geometry.y.to_numpy()
cx = cand_m.geometry.centroid.x.to_numpy()
cy = cand_m.geometry.centroid.y.to_numpy()

health_cap = np.zeros(n)
pop_flat = pop.ravel()
rows, cols = np.mgrid[0:hw[0], 0:hw[1]]
px = transform.c + (cols + 0.5) * transform.a
py = transform.f + (rows + 0.5) * transform.e
px, py = px.ravel(), py.ravel()

for i in range(n):
    d = np.hypot(hx - cx[i], hy - cy[i])
    in_range = d <= HEALTH_RADIUS_M
    supply = float(norms[in_range].sum())
    near = np.hypot(px - cx[i], py - cy[i]) <= HEALTH_RADIUS_M
    load = float(pop_flat[near].sum())
    health_cap[i] = max(0.0, supply - load)

# ---- INFRASTRUCTURE / ACCESSIBILITY -------------------------------------------
d_major = cand["distance_to_major_road_m"].to_numpy(float)
d_road = cand["distance_to_road_m"].to_numpy(float)
infra_cap = INFRA_CEILING * np.clip(1 - (d_major - 500) / (10000 - 500), 0.05, 1.0)
access_cap = ACCESS_CEILING * np.clip(1 - (d_road - 100) / (3000 - 100), 0.05, 1.0)

# ---- combine -------------------------------------------------------------------
constraints = {
    "land": land_cap, "infrastructure": infra_cap, "healthcare": health_cap,
    "environmental": env_cap, "accessibility": access_cap,
}
stack = np.vstack([constraints[k] for k in constraints])
effective = stack.min(axis=0)
binding_idx = stack.argmin(axis=0)
names = list(constraints)
current = cand["current_population"].to_numpy(float)
available = np.maximum(0.0, effective - current)

for k, v in constraints.items():
    cand[f"cap_{k}"] = np.round(v).astype(int)
cand["effective_capacity"] = np.round(effective).astype(int)
cand["available_capacity"] = np.round(available).astype(int)
cand["binding_constraint"] = [names[i] for i in binding_idx]
cand["developable_ha"] = developable_ha.round(1)
cand["mean_annual_rainfall_mm"] = mean_rain_mm.round(0)
cand["capacity_sources"] = json.dumps({
    "land": "DERIVED (slope raster) + CURATED density 100/ha",
    "infrastructure": "CURATED ceiling scaled by DERIVED road distance",
    "healthcare": "DERIVED (OSM facilities within 10 km, IPHS norms, minus existing load)",
    "environmental": "DERIVED (rainfall raster water yield) + CURATED runoff 0.15, 55 lpcd",
    "accessibility": "CURATED ceiling scaled by DERIVED road distance",
})

cand.to_file("data/processed/candidate_capacity.geojson", driver="GeoJSON")

# ---- report --------------------------------------------------------------------
print(f"\ncapacity computed for {n} candidates")
print("\nbinding constraint distribution:")
print(cand["binding_constraint"].value_counts().to_string())
feas = cand[cand["screening_status"] == "FEASIBLE"]
print(f"\nFEASIBLE candidates: {len(feas)}")
print(f"  total effective capacity {feas['effective_capacity'].sum():,}")
print(f"  total available capacity {feas['available_capacity'].sum():,}")
cols = ["candidate_id", "area_km2", "developable_ha", "cap_land", "cap_infrastructure",
        "cap_healthcare", "cap_environmental", "cap_accessibility",
        "effective_capacity", "current_population", "available_capacity",
        "binding_constraint"]
print("\ntop 8 by available capacity:")
print(cand.nlargest(8, "available_capacity")[cols].to_string(index=False))
print("\nwrote candidate_capacity.geojson")
