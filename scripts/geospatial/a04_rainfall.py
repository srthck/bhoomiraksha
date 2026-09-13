"""Monsoon rainfall climatology for Kangra.

Source: WorldClim 2.1 monthly precipitation, 2.5 arc-minute (~4.6 km),
1970-2000 normals (Fick & Hijmans 2017).

Why a climatology and not one year: landslide susceptibility is a measure of
predisposition, so the relevant rainfall input is the long-run monsoon regime,
not a single season's total. Kangra's south-west facing Dhauladhar slopes are
among the wettest places in India (Dharamshala ~3,000 mm/yr) while the
trans-Dhauladhar side is far drier — that orographic gradient is the signal
this layer contributes.

Resolution honesty: ~4.6 km cells across a 130 x 87 km district gives roughly
28 x 19 samples. That resolves the range-scale gradient, not hillslope detail.

Output: data/processed/rainfall_monsoon.tif — mean Jun-Sep total, mm,
resampled onto the 30 m analysis grid (values are interpolated, not refined).
"""
import os
import urllib.request
import zipfile

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_prec.zip"
ZIP = "data/raw/wc2.1_2.5m_prec.zip"
EXTRACT = "data/raw/worldclim_prec"
MONSOON = ("06", "07", "08", "09")  # Jun-Sep south-west monsoon
OUT = "data/processed/rainfall_monsoon.tif"

os.makedirs("data/raw", exist_ok=True)
if not os.path.exists(ZIP):
    print("downloading WorldClim 2.1 precipitation (2.5 arc-min, ~72 MB)…")
    urllib.request.urlretrieve(URL, ZIP)
print(f"archive: {os.path.getsize(ZIP) / 1e6:.1f} MB")

os.makedirs(EXTRACT, exist_ok=True)
with zipfile.ZipFile(ZIP) as z:
    wanted = [n for n in z.namelist() if any(n.endswith(f"_{m}.tif") for m in MONSOON)]
    for n in wanted:
        if not os.path.exists(os.path.join(EXTRACT, os.path.basename(n))):
            z.extract(n, EXTRACT)
print("monsoon months:", sorted(os.path.basename(n) for n in wanted))

# ---- sum the monsoon months -------------------------------------------------
total = None
for m in MONSOON:
    path = next(os.path.join(EXTRACT, f) for f in os.listdir(EXTRACT) if f.endswith(f"_{m}.tif"))
    with rasterio.open(path) as src:
        a = src.read(1).astype(np.float32)
        a = np.where(a < 0, np.nan, a)          # WorldClim uses -32768 over ocean
        total = a if total is None else total + a
        src_profile = src.profile
        src_transform, src_crs = src.transform, src.crs
print(f"global monsoon total: min {np.nanmin(total):.0f} max {np.nanmax(total):.0f} mm")

# ---- resample onto the analysis grid ---------------------------------------
with rasterio.open("data/processed/slope.tif") as ref:
    ref_profile = ref.profile
    dst = np.full((ref.height, ref.width), np.nan, np.float32)
    reproject(
        source=total, destination=dst,
        src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
        dst_transform=ref.transform, dst_crs=ref.crs, dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    mask_valid = np.isfinite(ref.read(1))

dst = np.where(mask_valid, dst, np.nan).astype(np.float32)
with rasterio.open(OUT, "w", **ref_profile) as out:
    out.write(dst, 1)
    out.update_tags(
        source="WorldClim 2.1, 2.5 arc-min, 1970-2000 normals",
        citation="Fick & Hijmans 2017, Int. J. Climatology",
        months="Jun-Sep", units="mm", native_resolution="~4.6 km",
        note="bilinearly resampled to the 30 m analysis grid; not refined",
    )

v = dst[np.isfinite(dst)]
print(f"\nKangra monsoon rainfall (Jun-Sep mean total):")
print(f"  min {v.min():.0f}  p25 {np.percentile(v,25):.0f}  median {np.median(v):.0f}  "
      f"p75 {np.percentile(v,75):.0f}  max {v.max():.0f} mm")
print(f"  spread across district: {v.max() - v.min():.0f} mm (orographic gradient)")
print(f"wrote {OUT}")
