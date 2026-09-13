"""Local hillshaded relief for the Kangra pilot region.

This is the command centre's base layer. It ships with the app, so the map
renders real terrain immediately and still renders if the remote vector
basemap is unreachable. Remote road/label layers are drawn on top of it.
"""
import concurrent.futures
import math
import os
import urllib.request

import numpy as np
from PIL import Image

Z, TS = 10, 256
WEST, EAST, SOUTH, NORTH = 74.0, 79.0, 29.8, 34.5
OUT_W = 2048
CACHE = "scripts/.cache/tiles10"


def lon2x(lon):
    return (lon + 180) / 360 * (1 << Z)


def lat2y(lat):
    r = math.radians(lat)
    return (0.5 - math.log(math.tan(math.pi / 4 + r / 2)) / (2 * math.pi)) * (1 << Z)


X0, X1 = int(lon2x(WEST)), int(lon2x(EAST))
Y0, Y1 = int(lat2y(NORTH)), int(lat2y(SOUTH))
NX, NY = X1 - X0 + 1, Y1 - Y0 + 1
print(f"z{Z} tiles x {X0}..{X1} y {Y0}..{Y1}  ({NX}x{NY} = {NX * NY})")

os.makedirs(CACHE, exist_ok=True)


def fetch(job):
    x, y = job
    path = f"{CACHE}/{x}_{y}.png"
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return None
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                open(path, "wb").write(r.read())
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

W, H = NX * TS, NY * TS
elev = np.zeros((H, W), np.float32)
for x in range(X0, X1 + 1):
    for y in range(Y0, Y1 + 1):
        a = np.asarray(Image.open(f"{CACHE}/{x}_{y}.png").convert("RGB")).astype(np.float32)
        e = (a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256) - 32768
        elev[(y - Y0) * TS:(y - Y0 + 1) * TS, (x - X0) * TS:(x - X0 + 1) * TS] = e

gy = (np.arange(H) + Y0 * TS) / (1 << Z)
lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * gy))))
LAT = lat[:, None].repeat(W, 1)


def blur(a, r=1):
    p = np.pad(a, r, mode="edge"); o = np.zeros_like(a); n = 0
    for i in range(2 * r + 1):
        for j in range(2 * r + 1):
            o += p[i:i + a.shape[0], j:j + a.shape[1]]; n += 1
    return o / n


res = 156543.03 / (1 << Z) * np.cos(np.radians(LAT))
az, alt = math.radians(318.0), math.radians(45.0)


def hillshade(src, zf):
    dy, dx = np.gradient(src)
    slope = np.arctan(zf * np.hypot(dx / res, dy / res))
    aspect = np.arctan2(-dx / res, dy / res)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)


shade = 0.58 * hillshade(blur(elev, 3), 1.6) + 0.42 * hillshade(blur(elev, 1), 4.5)
shade = 0.34 + 0.72 * shade ** 0.85


def ramp(stops, v):
    ks = np.array([s[0] for s in stops], np.float32)
    cs = np.array([s[1] for s in stops], np.float32)
    return np.stack([np.interp(v, ks, cs[:, c]) for c in range(3)], -1).astype(np.float32)


# A readable terrain surface: deep enough for a dark console, light enough
# that ridges, valleys and snow line are all legible. The console applies no
# extra filter over this layer, so what is baked here is what ships.
tint = [(0, (48, 68, 56)), (400, (58, 80, 62)), (900, (72, 90, 66)), (1800, (94, 100, 74)),
        (2800, (112, 108, 90)), (3800, (134, 128, 120)), (4800, (168, 168, 168)),
        (5800, (206, 208, 208)), (7000, (238, 240, 240))]

rgb = np.clip(ramp(tint, elev) * shade[..., None] * 1.18, 0, 255).astype(np.uint8)

TH = int(round(H * OUT_W / W))
Image.fromarray(rgb).resize((OUT_W, TH), Image.LANCZOS).save(
    "public/geo/pilot-relief.jpg", quality=82, optimize=True
)

# exact geographic corners of the raster, for the MapLibre image source
w = (X0 * TS) / (TS * (1 << Z)) * 360 - 180
e = ((X1 + 1) * TS) / (TS * (1 << Z)) * 360 - 180
n = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (Y0 / (1 << Z))))))
s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ((Y1 + 1) / (1 << Z))))))
print(f"pilot-relief.jpg {OUT_W}x{TH}")
print(f"BOUNDS west={w:.6f} east={e:.6f} north={n:.6f} south={s:.6f}")
