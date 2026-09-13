"""Landslide susceptibility index for Kangra — terrain- and rainfall-driven.

WHAT THIS IS
    A transparent, weighted-overlay susceptibility index built from real
    measured inputs (SRTM-derived slope and relief, WorldClim monsoon rainfall).

WHAT THIS IS NOT
    It is not a validated landslide prediction. No historical landslide
    inventory was obtainable for Kangra (see docs/data-inventory.md §4), so the
    weights below are expert judgement from the published literature, not
    calibrated against observed failures, and no skill score can be reported.
    The product must present this as a susceptibility index, never as a
    forecast or a probability.

FACTORS AND WHY EACH IS PRESENT

  Slope (weight 0.45)
      The dominant topographic control on shallow landsliding. The response is
      deliberately NOT linear: susceptibility rises steeply through the 15-35
      degree band, peaks around 35-45 degrees, then declines above ~55 degrees
      because very steep faces are typically bare rock that has already shed its
      regolith and has little material left to fail. A linear normalisation
      would wrongly rank cliff faces as the most susceptible terrain in the
      district.

  Monsoon rainfall (weight 0.30)
      The dominant trigger. Kangra spans an extreme orographic gradient — from
      ~215 mm to ~1,983 mm of Jun-Sep rainfall — so this genuinely discriminates
      within the district rather than acting as a constant.

  Local relief (weight 0.25)
      5x5 max-minus-min elevation, a ruggedness proxy standing in for slope
      length and terrain energy. Saturates at 200 m, beyond which additional
      relief does not meaningfully increase shallow-failure susceptibility.

WEIGHTS
      0.45 / 0.30 / 0.25, normalised to sum to 1. Ordering follows the standard
      predisposing-vs-triggering split in Himalayan landslide studies. These are
      documented judgement values; changing them changes the output, and
      docs/methodology.md records that they are uncalibrated.

Output: data/processed/landslide_susceptibility.tif  (0-100)
        data/processed/susceptibility_classes.tif    (1-5)
"""
import json

import numpy as np
import rasterio

WEIGHTS = {"slope": 0.45, "rainfall": 0.30, "relief": 0.25}

# Class breaks required by the product specification.
CLASS_BREAKS = [(0, 20, "Very Low"), (20, 40, "Low"), (40, 60, "Moderate"),
                (60, 80, "High"), (80, 100, "Very High")]


def read(path):
    with rasterio.open(path) as s:
        return s.read(1), s.profile


slope, profile = read("data/processed/slope.tif")
relief, _ = read("data/processed/relief.tif")
rain, _ = read("data/processed/rainfall_monsoon.tif")
valid = np.isfinite(slope) & np.isfinite(relief) & np.isfinite(rain)
print(f"grid {slope.shape}, {int(valid.sum()):,} valid cells")


def slope_susceptibility(deg):
    """Piecewise-linear slope response, peaking in the 35-45 degree band.

    Breakpoints (degrees -> susceptibility 0-1):
        0-10    0.00 -> 0.10   gentle; failures rare
        10-20   0.10 -> 0.45   regolith-mantled slopes begin to fail
        20-35   0.45 -> 0.95   the main shallow-landslide band
        35-45   0.95 -> 1.00   peak susceptibility
        45-60   1.00 -> 0.70   thinning regolith
        60-90   0.70 -> 0.35   predominantly bare rock faces
    """
    x = [0, 10, 20, 35, 45, 60, 90]
    y = [0.00, 0.10, 0.45, 0.95, 1.00, 0.70, 0.35]
    return np.interp(deg, x, y)


def normalise(a, lo, hi):
    """Linear min-max onto 0-1 using fixed, documented bounds.

    Fixed bounds rather than the observed range, so the index stays comparable
    if the study area is later extended beyond Kangra.
    """
    return np.clip((a - lo) / (hi - lo), 0, 1)


f_slope = slope_susceptibility(np.where(valid, slope, 0))
f_rain = normalise(np.where(valid, rain, 0), 200.0, 2000.0)   # district span, mm
f_relief = normalise(np.where(valid, relief, 0), 0.0, 200.0)  # saturates at 200 m

total_w = sum(WEIGHTS.values())
index = (WEIGHTS["slope"] * f_slope
         + WEIGHTS["rainfall"] * f_rain
         + WEIGHTS["relief"] * f_relief) / total_w
susceptibility = np.where(valid, index * 100.0, np.nan).astype(np.float32)

with rasterio.open("data/processed/landslide_susceptibility.tif", "w", **profile) as dst:
    dst.write(susceptibility, 1)
    dst.update_tags(
        model="weighted overlay, uncalibrated expert weights",
        factors="slope 0.45 (non-linear), monsoon rainfall 0.30, local relief 0.25",
        units="index 0-100",
        validated="NO - no landslide inventory available for Kangra",
        warning="susceptibility index, not a landslide forecast or probability",
    )

# ---- classification ----------------------------------------------------------
classes = np.full(susceptibility.shape, 0, np.uint8)
for i, (lo, hi, _) in enumerate(CLASS_BREAKS, start=1):
    classes = np.where(valid & (susceptibility >= lo) & (susceptibility < hi if hi < 100 else susceptibility <= hi),
                       i, classes)
cls_profile = {**profile, "dtype": "uint8", "nodata": 0}
with rasterio.open("data/processed/susceptibility_classes.tif", "w", **cls_profile) as dst:
    dst.write(classes, 1)
    dst.update_tags(classes="1 Very Low, 2 Low, 3 Moderate, 4 High, 5 Very High")

# ---- report ------------------------------------------------------------------
v = susceptibility[valid]
cell_km2 = (profile["transform"].a ** 2) / 1e6
print(f"\nsusceptibility index: min {v.min():.1f}  median {np.median(v):.1f}  "
      f"mean {v.mean():.1f}  max {v.max():.1f}")
print("\nclass distribution:")
summary = {}
for i, (lo, hi, label) in enumerate(CLASS_BREAKS, start=1):
    n = int((classes == i).sum())
    summary[label] = {"class": i, "cells": n, "area_km2": round(n * cell_km2, 1),
                      "pct": round(100 * n / valid.sum(), 1)}
    print(f"  {i} {label:10s} {n:>9,} cells  {n * cell_km2:7.0f} km2  {100 * n / valid.sum():5.1f} %")

print("\nfactor means over the district (0-1):")
for name, arr in (("slope", f_slope), ("rainfall", f_rain), ("relief", f_relief)):
    print(f"  {name:9s} {arr[valid].mean():.3f}")

json.dump({"weights": WEIGHTS, "classes": summary,
           "validated": False,
           "note": "uncalibrated weighted overlay; no landslide inventory available"},
          open("data/processed/susceptibility_summary.json", "w"), indent=1)
print("\nwrote landslide_susceptibility.tif, susceptibility_classes.tif")
