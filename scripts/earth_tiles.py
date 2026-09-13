"""Local Earth basemap for the globe phase of the entry sequence.

Source: NASA Visible Earth "Blue Marble" topography + bathymetry (public
domain). Reprojected from equirectangular to Web Mercator and cut into a
z0-z3 raster pyramid under public/geo/earth/, so the globe renders from local
assets and never depends on a remote tile service.

Beyond z3 MapLibre overzooms these tiles; by then the entry sequence has
already faded the layer out and the vector basemap carries the detail.
"""
import math
import os
import urllib.request

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC_URL = "https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x5400x2700.jpg"
SRC = "scripts/.cache/bluemarble.jpg"
OUT = "public/geo/earth"
BASE = 2048          # native size of the deepest level (z3 = 8x8 tiles)
MAX_Z = 3
TS = 256

os.makedirs("scripts/.cache", exist_ok=True)
if not os.path.exists(SRC):
    print("downloading Blue Marble…")
    urllib.request.urlretrieve(SRC_URL, SRC)

src = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
sh, sw = src.shape[:2]

# --- equirectangular -> Web Mercator -----------------------------------------
rows = np.arange(BASE)
y_norm = (rows + 0.5) / BASE
lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * y_norm))))
src_row = np.clip((90.0 - lat) / 180.0 * sh, 0, sh - 1)

lo = np.floor(src_row).astype(int)
hi = np.clip(lo + 1, 0, sh - 1)
frac = (src_row - lo)[:, None, None]

cols = np.clip(((np.arange(BASE) + 0.5) / BASE * sw).astype(int), 0, sw - 1)
merc = src[lo][:, cols] * (1 - frac) + src[hi][:, cols] * frac

# --- grade to the product palette --------------------------------------------
# Oceans go deeper and cooler, land keeps its natural colour but gains contrast
# so coastlines stay legible against the dark UI.
lum = merc @ np.array([0.299, 0.587, 0.114], np.float32)
blue_dominant = (merc[..., 2] > merc[..., 0] * 1.12) & (lum < 118)
ocean = blue_dominant[..., None]

graded = np.where(
    ocean,
    np.clip(merc * np.array([0.52, 0.72, 1.02], np.float32) * 0.86, 0, 255),
    np.clip((merc - 118) * 1.18 + 118 + np.array([6, 4, -4], np.float32), 0, 255),
)
graded = np.clip(graded, 0, 255).astype(np.uint8)
base_img = Image.fromarray(graded)

# --- cut the pyramid ----------------------------------------------------------
total_bytes = 0
count = 0
for z in range(MAX_Z + 1):
    n = 1 << z
    level = base_img.resize((n * TS, n * TS), Image.LANCZOS)
    for x in range(n):
        for y in range(n):
            d = f"{OUT}/{z}/{x}"
            os.makedirs(d, exist_ok=True)
            path = f"{d}/{y}.jpg"
            level.crop((x * TS, y * TS, (x + 1) * TS, (y + 1) * TS)).save(
                path, quality=80, optimize=True
            )
            total_bytes += os.path.getsize(path)
            count += 1

print(f"{count} tiles, {total_bytes / 1024:.0f} KB total, z0-z{MAX_Z}")
