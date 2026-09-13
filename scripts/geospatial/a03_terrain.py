"""Terrain preprocessing: validate -> reproject -> clip -> derive slope.

Slope is computed in a projected CRS (UTM 43N, metres). Computing it on a
geographic grid would treat 1 degree of longitude as 1 degree of latitude and
under-report slope by ~cos(latitude) in the x direction — about 15% at 32°N.

Outputs (all EPSG:32643, 30 m):
  data/processed/dem_kangra.tif    elevation, metres
  data/processed/slope.tif         slope, degrees
  data/processed/relief.tif        local relief, metres (max-min in 5x5)
"""
import json
import os

import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask
from rasterio.warp import Resampling, calculate_default_transform, reproject

SRC = "data/raw/dem_kangra_z12.tif"
CRS = "EPSG:32643"          # UTM 43N covers 72-78E; Kangra is 75.6-77.1E
RES = 30.0                  # metres, matches the SRTM source resolution
PLAUSIBLE = (100.0, 7000.0)  # anything outside this in Kangra is a void/artifact

os.makedirs("data/processed", exist_ok=True)
boundary = gpd.read_file("data/processed/kangra_boundary.geojson")

# ---- reproject to a metric grid --------------------------------------------
with rasterio.open(SRC) as src:
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src.crs, CRS, src.width, src.height, *src.bounds, resolution=RES
    )
    dem = np.empty((dst_h, dst_w), np.float32)
    reproject(
        source=rasterio.band(src, 1), destination=dem,
        src_transform=src.transform, src_crs=src.crs,
        dst_transform=dst_transform, dst_crs=CRS,
        resampling=Resampling.bilinear,
    )
print(f"reprojected to {CRS} @ {RES:.0f} m -> {dst_w}x{dst_h}")

profile = {
    "driver": "GTiff", "height": dst_h, "width": dst_w, "count": 1,
    "dtype": "float32", "crs": CRS, "transform": dst_transform,
    "nodata": np.nan, "compress": "deflate", "predictor": 2,
}

# ---- validate ---------------------------------------------------------------
bad = (dem < PLAUSIBLE[0]) | (dem > PLAUSIBLE[1])
print(f"validation: {int(bad.sum())} px outside {PLAUSIBLE} masked as nodata "
      f"({100 * bad.mean():.4f} %)")
dem = np.where(bad, np.nan, dem)

# ---- derive terrain on the FULL grid, then clip --------------------------
# Deriving after clipping would leave every pixel on the district edge with a
# NaN neighbour and therefore a NaN slope. The padded DEM has valid neighbours
# everywhere, so slope is correct right up to the boundary.
full = np.isfinite(dem)
H, W = dem.shape
pad = np.pad(np.where(full, dem, np.nan), 1, mode="edge")


def s_(dy, dx):
    return pad[1 + dy: 1 + dy + H, 1 + dx: 1 + dx + W]


# Horn (1981) 3x3 weighted difference — the standard used by GDAL/ArcGIS/QGIS.
dz_dx = ((s_(-1, 1) + 2 * s_(0, 1) + s_(1, 1)) - (s_(-1, -1) + 2 * s_(0, -1) + s_(1, -1))) / (8 * RES)
dz_dy = ((s_(1, -1) + 2 * s_(1, 0) + s_(1, 1)) - (s_(-1, -1) + 2 * s_(-1, 0) + s_(-1, 1))) / (8 * RES)
slope_full = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)

p2 = np.pad(np.where(full, dem, np.nan), 2, mode="edge")
stack = np.stack([p2[2 + dy: 2 + dy + H, 2 + dx: 2 + dx + W]
                  for dy in range(-2, 3) for dx in range(-2, 3)])
with np.errstate(invalid="ignore"):
    relief_full = (np.nanmax(stack, 0) - np.nanmin(stack, 0)).astype(np.float32)
del stack, p2, pad

# ---- clip everything to the district ---------------------------------------
shapes = list(boundary.to_crs(CRS).geometry)
layers = {"dem_kangra": dem, "slope": slope_full, "relief": relief_full}
clipped = {}
for name, arr in layers.items():
    tmp = f"data/processed/_tmp_{name}.tif"
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(arr, 1)
    with rasterio.open(tmp) as src:
        out, transform_c = mask(src, shapes, crop=True, nodata=np.nan, filled=True)
    clipped[name] = out[0].astype(np.float32)
    os.remove(tmp)

dem_c = clipped["dem_kangra"]
slope = clipped["slope"]
relief = clipped["relief"]
h, w = dem_c.shape
inside = np.isfinite(dem_c)
print(f"clipped to Kangra -> {w}x{h}, {int(inside.sum())} valid px "
      f"({inside.sum() * RES * RES / 1e6:.0f} km2)")
print(f"elevation  min {np.nanmin(dem_c):.0f}  p1 {np.nanpercentile(dem_c, 1):.0f}  "
      f"median {np.nanmedian(dem_c):.0f}  max {np.nanmax(dem_c):.0f} m")

prof_c = {**profile, "height": h, "width": w, "transform": transform_c}
tags = {
    "dem_kangra": dict(source="AWS Terrain Tiles (Mapzen) z12, SRTM-derived",
                       units="metres", resolution_m=str(RES), acquired="2026-09-10"),
    "slope": dict(method="Horn 1981 3x3", units="degrees", derived_from="dem_kangra.tif"),
    "relief": dict(method="5x5 max-min", units="metres", derived_from="dem_kangra.tif"),
}
for name, arr in clipped.items():
    with rasterio.open(f"data/processed/{name}.tif", "w", **prof_c) as dst:
        dst.write(np.where(inside, arr, np.nan).astype(np.float32), 1)
        dst.update_tags(**tags[name])

# ---- report -----------------------------------------------------------------
sv = slope[inside]
sv = sv[np.isfinite(sv)]
print(f"\nslope distribution (degrees), n={sv.size} of {int(inside.sum())} in-district px:")
for p in (5, 25, 50, 75, 90, 95, 99):
    print(f"  p{p:<3d} {np.percentile(sv, p):5.1f}")
print(f"  mean {sv.mean():.1f}   max {sv.max():.1f}")
print(f"  >30 deg: {100 * (sv > 30).mean():.1f} % of district")
print(f"  >45 deg: {100 * (sv > 45).mean():.1f} % of district")
rv = relief[inside]
rv = rv[np.isfinite(rv)]
print(f"\nrelief 5x5 (m): median {np.median(rv):.0f}  p95 {np.percentile(rv, 95):.0f}")

json.dump({"crs": CRS, "resolution_m": RES, "width": w, "height": h,
           "valid_px": int(inside.sum()), "area_km2": float(inside.sum() * RES * RES / 1e6)},
          open("data/processed/grid.json", "w"), indent=1)
print("\nwrote dem_kangra.tif, slope.tif, relief.tif, grid.json")
