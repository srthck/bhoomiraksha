"""Wide terrain backdrop, rendered in the same projection as the India hero so
the two stay in register when the page overlays them."""
import numpy as np
from PIL import Image

Z, TS = 6, 256
X0, X1, Y0, Y1 = 41, 51, 22, 33
W, H = (X1 - X0 + 1) * TS, (Y1 - Y0 + 1) * TS

elev = np.zeros((H, W), np.float32)
for tx in range(X0, X1 + 1):
    for ty in range(Y0, Y1 + 1):
        a = np.asarray(Image.open(f"tiles/{Z}_{tx}_{ty}.png").convert("RGB")).astype(np.float32)
        e = (a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256) - 32768
        elev[(ty - Y0) * TS:(ty - Y0 + 1) * TS, (tx - X0) * TS:(tx - X0 + 1) * TS] = e

WORLD = TS * (1 << Z)
gy = (np.arange(H) + Y0 * TS) / WORLD
lon = ((np.arange(W) + X0 * TS) / WORLD) * 360 - 180
lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * gy))))
LAT, LON = lat[:, None].repeat(W, 1), lon[None, :].repeat(H, 0)


def blur(a, r=1):
    p = np.pad(a, r, mode="edge"); o = np.zeros_like(a); n = 0
    for i in range(2 * r + 1):
        for j in range(2 * r + 1):
            o += p[i:i + a.shape[0], j:j + a.shape[1]]; n += 1
    return o / n


res = 156543.03 / (1 << Z) * np.cos(np.radians(LAT))
az, alt = np.radians(318.0), np.radians(44.0)


def hillshade(src, zf):
    dy, dx = np.gradient(src)
    slope = np.arctan(zf * np.hypot(dx / res, dy / res))
    aspect = np.arctan2(-dx / res, dy / res)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)


shade = 0.62 * hillshade(blur(elev, 3), 2.6) + 0.38 * hillshade(blur(elev, 1), 9.0)
shade = 0.46 + 0.60 * shade ** 0.80


def ramp(stops, v):
    ks = np.array([s[0] for s in stops], np.float32)
    cs = np.array([s[1] for s in stops], np.float32)
    return np.stack([np.interp(v, ks, cs[:, c]) for c in range(3)], -1).astype(np.float32)


land_wet = [(0, (34, 80, 50)), (120, (52, 102, 56)), (350, (74, 118, 58)), (800, (108, 130, 66)),
            (1600, (146, 138, 84)), (2600, (148, 118, 86)), (3800, (140, 114, 102)),
            (4800, (184, 176, 174)), (5600, (230, 230, 228)), (7000, (255, 255, 255))]
land_dry = [(0, (146, 128, 82)), (120, (174, 148, 90)), (350, (190, 158, 94)), (800, (184, 154, 96)),
            (1600, (174, 140, 94)), (2600, (158, 122, 90)), (3800, (148, 118, 104)),
            (4800, (188, 180, 176)), (5600, (234, 234, 232)), (7000, (255, 255, 255))]
sea = [(-6000, (8, 34, 68)), (-3000, (10, 46, 90)), (-1200, (13, 62, 108)), (-400, (18, 84, 130)),
       (-120, (26, 108, 152)), (-30, (38, 134, 172)), (0, (52, 158, 190))]

dry = np.clip((78.5 - LON) / 9.0, 0, 1) * np.clip((LAT - 20.0) / 6.0, 0, 1)
dry = np.maximum(dry, np.clip((72.5 - LON) / 5.0, 0, 1) * np.clip((LAT - 22.0) / 4.0, 0, 1))
dry = np.clip(dry, 0, 1)[..., None]

land = ramp(land_wet, elev) * (1 - dry) + ramp(land_dry, elev) * dry
ocean = ramp(sea, np.clip(elev, -6000, 0))
rgb = np.where((elev > 0)[..., None], land * shade[..., None], ocean * (0.86 + 0.14 * shade[..., None]))
shelf = np.clip((elev + 180) / 180, 0, 1) * (elev <= 0)
rgb = np.clip(rgb + shelf[..., None] * np.array([6, 26, 30], np.float32), 0, 255)


def sat(a, k):
    g = a @ np.array([0.299, 0.587, 0.114], np.float32)
    return np.clip(g[..., None] + (a - g[..., None]) * k, 0, 255)


# A bright, sunny environment: the backdrop still recedes behind the India
# plate, but by desaturation and a cool cast rather than by going dark. The
# landing's left-hand scrim, not a dim raster, is what keeps the copy legible.
ctx = sat(rgb, 0.84) * 0.86
ctx = np.clip(ctx + np.array([8, 20, 34], np.float32), 0, 255).astype(np.uint8)

TW = 1800
TH = int(round(H * TW / W))
Image.fromarray(ctx).resize((TW, TH), Image.LANCZOS).save("india-context-wide.jpg", quality=84, optimize=True)

# placement of this raster relative to the hero plate box, in plate-box percent
PX0, PY0, PW, PH = 140, 210, 1640, 1720          # hero crop, in hero-mosaic pixels
HX0, HY0 = 43 * TS, 24 * TS                       # hero mosaic origin, world pixels
WX0, WY0 = X0 * TS, Y0 * TS                       # wide mosaic origin, world pixels
off_x = (WX0 - HX0) - PX0                         # wide origin in hero-crop pixel space
off_y = (WY0 - HY0) - PY0
print(f"size {TW}x{TH}")
print(f"left  {off_x / PW * 100:.3f}%")
print(f"top   {off_y / PH * 100:.3f}%")
print(f"width {W / PW * 100:.3f}%")
print(f"height{H / PH * 100:.3f}%")
