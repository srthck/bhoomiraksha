import numpy as np
from PIL import Image

rgb = np.load("rgb.npy"); mask = np.load("mask.npy")
CX0, CX1, CY0, CY1 = 140, 1780, 210, 1930
rgb = rgb[CY0:CY1, CX0:CX1]; mask = mask[CY0:CY1, CX0:CX1]
h, w = mask.shape
print("crop", w, h)

def sat(a, k):
    g = a @ np.array([0.299, 0.587, 0.114], np.float32)
    return np.clip(g[..., None] + (a - g[..., None]) * k, 0, 255)

# --- India: brighter, richer, slightly lifted blacks -------------------------
hero = sat(rgb, 1.16)
hero = np.clip(hero * 1.10 + 6, 0, 255)
hero_rgba = np.dstack([hero, mask * 255]).astype(np.uint8)

# --- context: cooler, darker, receding --------------------------------------
ctx = sat(rgb, 0.62) * 0.50
ctx = np.clip(ctx + np.array([2, 10, 20], np.float32) * 0.9, 0, 255)
# push the surrounding land even further back, keep the ocean readable
ctx = np.where((mask > 0.5)[..., None], ctx * 0.85, ctx)

TW = 1400
TH = int(round(h * TW / w))
Image.fromarray(hero_rgba).resize((TW, TH), Image.LANCZOS).save("india-hero.png")
Image.fromarray(ctx.astype(np.uint8)).resize((TW, TH), Image.LANCZOS).save("india-context.jpg", quality=86, optimize=True)
print("out", TW, TH)
