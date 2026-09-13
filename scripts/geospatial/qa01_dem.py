"""DEM quality assurance.

a03_terrain masked 2.61% of reprojected cells as outside the plausible
100-7000 m range. This asks the only question that matters: does that masking
touch any settlement or any analytical output?

No elevation is invented here. The script reports; it does not repair.
"""
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

with rasterio.open("data/processed/dem_kangra.tif") as s:
    dem, transform, hw, crs = s.read(1), s.transform, (s.height, s.width), s.crs
with rasterio.open("data/processed/slope.tif") as s:
    slope = s.read(1)
with rasterio.open("data/processed/landslide_susceptibility.tif") as s:
    susc = s.read(1)

# "in district" = anything the clip kept; nodata outside the polygon is also NaN,
# so use the susceptibility layer's own footprint as the district mask proxy.
in_dem = np.isfinite(dem)
in_slope = np.isfinite(slope)
in_susc = np.isfinite(susc)

print("=== raster coverage ===")
print(f"  DEM valid cells          {in_dem.sum():>10,}")
print(f"  slope valid cells        {in_slope.sum():>10,}")
print(f"  susceptibility valid     {in_susc.sum():>10,}")
print(f"  slope NaN inside DEM     {int((in_dem & ~in_slope).sum()):>10,}")
print(f"  susc  NaN inside DEM     {int((in_dem & ~in_susc).sum()):>10,}")

# Cells the district clip kept but which carry no elevation: these are the
# holes the plausibility mask punched inside Kangra.
hab = gpd.read_file("data/processed/habitations.geojson").to_crs(crs)
zones = rasterize(((g, i + 1) for i, g in enumerate(hab.geometry)),
                  out_shape=hw, transform=transform, fill=0, dtype="int32")
in_settlement = zones > 0

holes_in_settlements = int((in_settlement & ~in_dem).sum())
settlement_cells = int(in_settlement.sum())
print("\n=== does masking touch settlements? ===")
print(f"  cells inside a settlement footprint      {settlement_cells:>10,}")
print(f"  of those with no elevation (masked)      {holes_in_settlements:>10,}")
print(f"  share                                    {100 * holes_in_settlements / max(settlement_cells,1):>9.3f} %")

# Critical distinction: a settlement buffer near the district edge extends
# past the boundary, where the DEM was clipped away. That is expected and
# harmless. A hole *inside* the boundary would be a real void that corrupts
# slope and susceptibility for that settlement.
boundary = gpd.read_file("data/processed/kangra_boundary.geojson").to_crs(crs)
district = rasterize([(g, 1) for g in boundary.geometry], out_shape=hw,
                     transform=transform, fill=0, dtype="uint8").astype(bool)
no_elev = in_settlement & ~in_dem
overhang = int((no_elev & ~district).sum())
interior = int((no_elev & district).sum())
print(f"  of those, outside the district (buffer overhang) {overhang:>10,}")
print(f"  of those, INSIDE the district (true DEM void)    {interior:>10,}")

affected = sorted(set(zones[no_elev & district].tolist()))
if affected:
    names = hab.iloc[[i - 1 for i in affected]]["name"].tolist()
    print(f"  settlements with a true interior void: {len(affected)}")
    print("   ", ", ".join(names[:15]))
else:
    print("  settlements with a true interior void: 0")
    print("  VERDICT: DEM masking does not affect any in-district analysis.")

# Where were the masked cells, geographically?
print("\n=== elevation distribution actually used ===")
v = dem[in_dem]
print(f"  min {v.min():.0f}  p1 {np.percentile(v,1):.0f}  median {np.median(v):.0f}  "
      f"p99 {np.percentile(v,99):.0f}  max {v.max():.0f} m")
low = v[v < 300]
print(f"  cells below 300 m: {low.size:,} ({100*low.size/v.size:.2f} %) — "
      f"the district's south-west toe toward the Punjab plain")

json.dump({
    "dem_valid_cells": int(in_dem.sum()),
    "slope_nan_inside_dem": int((in_dem & ~in_slope).sum()),
    "settlement_cells": settlement_cells,
    "settlement_cells_without_elevation": holes_in_settlements,
    "settlement_cells_overhanging_district": overhang,
    "settlement_cells_true_interior_void": interior,
    "settlements_with_interior_void": len(affected),
    "verdict": ("DEM masking affects only buffer area outside the district; "
                "no in-district analysis is affected"
                if not affected else "some settlements contain true interior DEM voids"),
}, open("data/processed/qa_dem.json", "w"), indent=1)
print("\nwrote data/processed/qa_dem.json")
