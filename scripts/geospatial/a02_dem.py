"""Acquire a real DEM for the Kangra study area at native resolution.

Source: AWS Terrain Tiles (Mapzen), terrarium encoding, zoom 12. Over India the
underlying elevation is SRTM (~30 m); zoom 12 is ~26 m/px at 32°N, so this is
the first zoom that does not throw away source detail.

The z10 tiles already cached in the repo are ~130 m/px and were only ever built
for the console's background raster. Slope from a 130 m grid systematically
under-reports the steep, short slopes that actually fail, so they are not used
here.

Output: data/raw/dem_kangra_z12.tif — elevation in metres, EPSG:4326.
"""
import concurrent.futures
import json
import math
import os
import urllib.request

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

Z, TS = 12, 256
PAD = 0.06  # degrees of margin so edge slope/focal windows stay valid
CACHE = "scripts/.cache/tiles12"
OUT = "data/raw/dem_kangra_z12.tif"

bbox = json.load(open("data/processed/kangra_bbox.json"))
WEST, EAST = bbox["west"] - PAD, bbox["east"] + PAD
SOUTH, NORTH = bbox["south"] - PAD, bbox["north"] + PAD


def lon2x(lon):
    return (lon + 180) / 360 * (1 << Z)


def lat2y(lat):
    r = math.radians(lat)
    return (0.5 - math.log(math.tan(math.pi / 4 + r / 2)) / (2 * math.pi)) * (1 << Z)


def x2lon(x):
    return x / (1 << Z) * 360 - 180


def y2lat(y):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << Z)))))


X0, X1 = int(lon2x(WEST)), int(lon2x(EAST))
Y0, Y1 = int(lat2y(NORTH)), int(lat2y(SOUTH))
NX, NY = X1 - X0 + 1, Y1 - Y0 + 1
print(f"z{Z}: x {X0}..{X1}, y {Y0}..{Y1} -> {NX}x{NY} = {NX * NY} tiles")

os.makedirs(CACHE, exist_ok=True)
os.makedirs("data/raw", exist_ok=True)


def fetch(job):
    x, y = job
    p = f"{CACHE}/{x}_{y}.png"
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return None
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                open(p, "wb").write(r.read())
            return None
        except Exception as exc:
            err = exc
    return f"{x},{y}: {err}"


jobs = [(x, y) for x in range(X0, X1 + 1) for y in range(Y0, Y1 + 1)]
with concurrent.futures.ThreadPoolExecutor(16) as ex:
    bad = [b for b in ex.map(fetch, jobs) if b]
print(f"fetched {len(jobs)} tiles, {len(bad)} failed")
for b in bad[:5]:
    print("  ", b)
if bad:
    raise SystemExit("DEM incomplete — refusing to write a partial elevation raster")

H, W = NY * TS, NX * TS
elev = np.zeros((H, W), np.float32)
for x in range(X0, X1 + 1):
    for y in range(Y0, Y1 + 1):
        a = np.asarray(Image.open(f"{CACHE}/{x}_{y}.png").convert("RGB")).astype(np.float32)
        elev[(y - Y0) * TS:(y - Y0 + 1) * TS, (x - X0) * TS:(x - X0 + 1) * TS] = (
            a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256
        ) - 32768

w, e = x2lon(X0), x2lon(X1 + 1)
n, s = y2lat(Y0), y2lat(Y1 + 1)
transform = from_bounds(w, s, e, n, W, H)

with rasterio.open(
    OUT, "w", driver="GTiff", height=H, width=W, count=1, dtype="float32",
    crs="EPSG:4326", transform=transform, compress="deflate", predictor=2,
) as dst:
    dst.write(elev, 1)
    dst.update_tags(
        source="AWS Terrain Tiles (Mapzen) terrarium, zoom 12",
        underlying="SRTM ~30 m over India",
        units="metres",
        acquired="2026-09-10",
    )

print(f"\n{OUT}: {W}x{H}, {os.path.getsize(OUT)/1e6:.1f} MB")
print(f"bounds  W {w:.5f}  S {s:.5f}  E {e:.5f}  N {n:.5f}")
print(f"elev    min {elev.min():.0f} m   max {elev.max():.0f} m   mean {elev.mean():.0f} m")
print("sanity: Kangra valley floor ~600 m, Dhauladhar crest ~4,500-5,600 m")
