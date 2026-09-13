"""The allocation must not depend on input ordering.

Rebuilds the Voronoi-clipped allocation with settlements in shuffled order and
asserts every settlement receives an identical cell count and population.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.features import rasterize
from rasterio.windows import Window, transform as win_tf

RADII = {"city": 2500, "town": 1200, "suburb": 800, "village": 500, "hamlet": 250}


def allocate(hab, transform, shape_hw):
    H, W = shape_hw
    best = np.full((H, W), np.inf, np.float32)
    owner = np.zeros((H, W), np.int64)
    inv = ~transform
    for key, geom, centre in zip(hab["key"], hab.geometry, hab["centre"]):
        minx, miny, maxx, maxy = geom.bounds
        c0, r0 = inv * (minx, maxy); c1, r1 = inv * (maxx, miny)
        c0, r0 = max(int(np.floor(c0)) - 1, 0), max(int(np.floor(r0)) - 1, 0)
        c1, r1 = min(int(np.ceil(c1)) + 1, W), min(int(np.ceil(r1)) + 1, H)
        if c1 <= c0 or r1 <= r0:
            continue
        wt = win_tf(Window(c0, r0, c1 - c0, r1 - r0), transform)
        m = rasterize([(geom, 1)], out_shape=(r1 - r0, c1 - c0), transform=wt,
                      fill=0, dtype="uint8").astype(bool)
        if not m.any():
            continue
        rows, cols = np.nonzero(m)
        xs = wt.c + (cols + 0.5) * wt.a
        ys = wt.f + (rows + 0.5) * wt.e
        d = np.hypot(xs - centre.x, ys - centre.y).astype(np.float32)
        gr, gc = rows + r0, cols + c0
        b = d < best[gr, gc]
        best[gr[b], gc[b]] = d[b]
        owner[gr[b], gc[b]] = key
    return owner


def build():
    s = gpd.read_file("data/processed/settlements.geojson")
    with rasterio.open("data/processed/landslide_susceptibility.tif") as r:
        crs, transform, hw = r.crs, r.transform, (r.height, r.width)
    pts = s.to_crs(crs).reset_index(drop=True)
    pts["centre"] = pts.geometry
    pts["key"] = pts["osm_id"].astype(np.int64)
    pts["geometry"] = [p.buffer(RADII.get(c or "village", 500))
                       for p, c in zip(pts.geometry, pts["place"])]
    return pts, transform, hw


def test_allocation_is_order_independent():
    hab, transform, hw = build()
    with rasterio.open("data/processed/population.tif") as r:
        pop = np.nan_to_num(r.read(1)).ravel()

    def stats(df):
        owner = allocate(df, transform, hw).ravel()
        sel = owner > 0
        keys, inv = np.unique(owner[sel], return_inverse=True)
        return dict(zip(keys.tolist(),
                        np.bincount(inv, weights=pop[sel]).round(3).tolist()))

    a = stats(hab)
    b = stats(hab.sample(frac=1.0, random_state=7).reset_index(drop=True))
    c = stats(hab.iloc[::-1].reset_index(drop=True))

    assert a.keys() == b.keys() == c.keys(), "different settlements received cells"
    for k in a:
        assert abs(a[k] - b[k]) < 1e-6, f"shuffle changed settlement {k}: {a[k]} vs {b[k]}"
        assert abs(a[k] - c[k]) < 1e-6, f"reverse changed settlement {k}: {a[k]} vs {c[k]}"
    print(f"OK: {len(a)} settlements identical across original, shuffled and reversed order")


if __name__ == "__main__":
    test_allocation_is_order_independent()
