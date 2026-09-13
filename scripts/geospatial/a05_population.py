"""Gridded population for Kangra.

Source: GHSL GHS-POP R2023A, epoch 2020, 100 m, Mollweide (ESRI:54009).
Kangra spans two GHSL tiles: R6_C25 and R6_C26.

This is a *modelled* population grid (built from census tables redistributed
using built-up surface), not the Indian Census itself. Village-level Census
2011 counts are not openly available in machine-readable form. Every population
figure downstream must therefore be described as a gridded estimate.

Conservation of counts: GHS-POP cells hold persons *per cell*, so the raster
cannot be resampled directly — changing cell size would change the totals.
This converts to density (persons/m2), reprojects the density, then multiplies
by the target cell area, which preserves the population total.

Validation: Census 2011 recorded 1,510,075 people in Kangra district. The
GHSL 2020 estimate should land in the same neighbourhood.

Output: data/processed/population.tif — persons per 30 m cell.
"""
import os
import urllib.request
import zipfile

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject

BASE = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
        "GHS_POP_E2020_GLOBE_R2023A_54009_100/V1-0/tiles/")
STEM = "GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_"
TILES = ("R6_C25", "R6_C26")
RAW = "data/raw/ghsl"
OUT = "data/processed/population.tif"
SRC_CELL_M = 100.0

os.makedirs(RAW, exist_ok=True)
paths = []
for t in TILES:
    z = f"{RAW}/{STEM}{t}.zip"
    if not os.path.exists(z):
        print(f"downloading GHSL {t}…")
        urllib.request.urlretrieve(f"{BASE}{STEM}{t}.zip", z)
    with zipfile.ZipFile(z) as zf:
        tif = next(n for n in zf.namelist() if n.endswith(".tif"))
        target = os.path.join(RAW, os.path.basename(tif))
        if not os.path.exists(target):
            zf.extract(tif, RAW)
        paths.append(target)
    print(f"  {t}: {os.path.getsize(z) / 1e6:.0f} MB")

srcs = [rasterio.open(p) for p in paths]
mosaic, mosaic_transform = merge(srcs)
src_crs = srcs[0].crs
src_nodata = srcs[0].nodata
for s in srcs:
    s.close()

pop = mosaic[0].astype(np.float64)
pop = np.where((pop == src_nodata) | (pop < 0), 0.0, pop)
print(f"mosaic {pop.shape}, total persons in the two tiles: {pop.sum():,.0f}")

# persons per cell -> persons per m2, so reprojection conserves the total
density = pop / (SRC_CELL_M * SRC_CELL_M)

with rasterio.open("data/processed/slope.tif") as ref:
    ref_profile = ref.profile
    dst_cell = abs(ref.transform.a)
    dens_out = np.zeros((ref.height, ref.width), np.float64)
    reproject(
        source=density, destination=dens_out,
        src_transform=mosaic_transform, src_crs=src_crs, src_nodata=None,
        dst_transform=ref.transform, dst_crs=ref.crs,
        resampling=Resampling.average,
    )
    valid = np.isfinite(ref.read(1))

pop_out = (dens_out * dst_cell * dst_cell).astype(np.float32)
pop_out = np.where(valid, pop_out, np.nan).astype(np.float32)

with rasterio.open(OUT, "w", **ref_profile) as out:
    out.write(pop_out, 1)
    out.update_tags(
        source="GHSL GHS-POP R2023A, epoch 2020, 100 m, Mollweide",
        licence="CC BY 4.0, European Commission JRC",
        units=f"persons per {dst_cell:.0f} m cell",
        method="counts -> density -> reproject(average) -> counts, total-preserving",
        note="modelled population grid, not the Indian Census",
    )

total = float(np.nansum(pop_out))
print(f"\nKangra district population (GHSL 2020 estimate): {total:,.0f}")
print(f"Census 2011 recorded:                            1,510,075")
print(f"difference: {100 * (total - 1510075) / 1510075:+.1f} %")
occupied = np.isfinite(pop_out) & (pop_out > 0.01)
print(f"populated cells: {occupied.sum():,} of {valid.sum():,} "
      f"({100 * occupied.sum() / valid.sum():.1f} % of district)")
print(f"wrote {OUT}")
