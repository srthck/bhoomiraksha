"""Exposure engine: hazard x habitation x population.

Intersects the susceptibility surface with settlement footprints and the
population grid to answer, per settlement: how much of it sits in hazardous
terrain, and how many people that is.

HABITATION FOOTPRINTS
    OSM place records are usually points, which have no area to intersect.
    Two sources are used, and every row records which:

      osm_polygon   a real OSM residential/village polygon contains the place
                    node — the footprint is that polygon.
      buffer_approx no polygon available — a circular buffer sized by
                    settlement class. An APPROXIMATION of extent, flagged so
                    downstream consumers can discount it.

    Buffer radii (documented judgement): city 2500 m, town 1200 m,
    suburb 800 m, village 500 m, hamlet 250 m.

DETERMINISTIC ALLOCATION (the fix)
    Footprints overlap — the Dharamshala / McLeod Ganj / Bhagsu / Forsyth Ganj
    cluster is the obvious case. Rasterising them all into one zone grid gave
    each shared cell to whichever settlement happened to be rasterised LAST,
    so per-settlement population depended on input order.

    Now each cell is allocated to the settlement whose CENTRE is nearest,
    among those whose footprint actually contains the cell. That is a Voronoi
    partition clipped to the footprints: deterministic, order-independent,
    geographically defensible, and it still cannot double-count a person.

    The original footprint geometry is preserved. The allocation zone is
    reported alongside it (`allocated_area_km2` vs `footprint_area_km2`), so
    the difference is visible rather than silent.

DISTRICT vs SETTLEMENT EXPOSURE
    These are different numbers and must never be conflated:
      - district exposure  = all population in the district, in hazard terrain
      - settlement exposure = population inside settlement footprints only
    Both are written to data/processed/exposure_summary.json.

Output: data/processed/habitations.geojson
        data/processed/exposure_summary.json
"""
import json
import os
import time
import urllib.parse
import urllib.request

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import Polygon

HIGH_BREAK = 60.0  # susceptibility >= 60 is "High" or "Very High"
RADII = {"city": 2500, "town": 1200, "suburb": 800, "village": 500, "hamlet": 250}

bbox = json.load(open("data/processed/kangra_bbox.json"))
BB = f"{bbox['south']:.5f},{bbox['west']:.5f},{bbox['north']:.5f},{bbox['east']:.5f}"

# ---- real settlement polygons where OSM has them -----------------------------
RAW = "data/raw/osm_residential.json"
if not os.path.exists(RAW):
    q = f"""[out:json][timeout:300];
        (way["landuse"~"^(residential|village_green)$"]({BB});
         way["place"~"^(village|hamlet|town|city|suburb)$"]({BB});
         relation["landuse"="residential"]({BB}););
        out geom;"""
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter"):
        try:
            req = urllib.request.Request(
                ep, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "bhoomi-raksha-pilot/1.0 (research)"})
            with urllib.request.urlopen(req, timeout=300) as r:
                json.dump(json.loads(r.read().decode()), open(RAW, "w", encoding="utf-8"))
            break
        except Exception as e:
            print(f"  residential polygons via {ep.split('/')[2]} failed: {e}")
            time.sleep(5)

polys = []
if os.path.exists(RAW):
    for el in json.load(open(RAW, encoding="utf-8")).get("elements", []):
        g = el.get("geometry")
        if not g or len(g) < 4:
            continue
        try:
            p = Polygon([(q["lon"], q["lat"]) for q in g])
            if p.is_valid and p.area > 0:
                polys.append(p)
        except Exception:
            continue
print(f"OSM settlement polygons available: {len(polys)}")
poly_gdf = gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326") if polys else None

# ---- build one footprint per settlement --------------------------------------
settlements = gpd.read_file("data/processed/settlements.geojson")
with rasterio.open("data/processed/landslide_susceptibility.tif") as s:
    CRS, transform, shape_hw = s.crs, s.transform, (s.height, s.width)
    susc = s.read(1)
CELL = abs(transform.a)
CELL_AREA = CELL * CELL

pts = settlements.to_crs(CRS).reset_index(drop=True)
polys_m = poly_gdf.to_crs(CRS) if poly_gdf is not None else None
sindex = polys_m.sindex if polys_m is not None else None

footprints, sources = [], []
for i, pt in enumerate(pts.geometry):
    chosen = None
    if polys_m is not None:
        for idx in sindex.query(pt, predicate="within"):
            chosen = polys_m.geometry.iloc[idx]
            break
    if chosen is not None:
        footprints.append(chosen)
        sources.append("osm_polygon")
    else:
        r = RADII.get(pts.at[i, "place"] or "village", 500)
        footprints.append(pt.buffer(r))
        sources.append("buffer_approx")

hab = pts.copy()
hab["centre"] = pts.geometry           # place node, used as the Voronoi seed
hab["geometry"] = footprints
hab["footprint_source"] = sources
hab["footprint_area_km2"] = (hab.geometry.area / 1e6).round(4)
print(f"footprints: {sources.count('osm_polygon')} from OSM polygons, "
      f"{sources.count('buffer_approx')} approximated by buffer")

# ---- deterministic allocation: nearest centre among containing footprints ----
# Implemented per settlement over its own window, keeping a running minimum of
# distance-to-centre. Order cannot affect the outcome because the comparison is
# strictly on distance (ties resolved by lower index, which is stable).
H, W = shape_hw
best_dist = np.full((H, W), np.inf, np.float32)
owner = np.zeros((H, W), np.int32)

inv = ~transform
for i, (geom, centre) in enumerate(zip(hab.geometry, hab["centre"]), start=1):
    minx, miny, maxx, maxy = geom.bounds
    c0, r0 = inv * (minx, maxy)
    c1, r1 = inv * (maxx, miny)
    c0, r0 = max(int(np.floor(c0)) - 1, 0), max(int(np.floor(r0)) - 1, 0)
    c1, r1 = min(int(np.ceil(c1)) + 1, W), min(int(np.ceil(r1)) + 1, H)
    if c1 <= c0 or r1 <= r0:
        continue
    win_transform = rasterio.windows.transform(
        rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0), transform)
    m = rasterize([(geom, 1)], out_shape=(r1 - r0, c1 - c0),
                  transform=win_transform, fill=0, dtype="uint8").astype(bool)
    if not m.any():
        continue
    rows, cols = np.nonzero(m)
    xs = win_transform.c + (cols + 0.5) * win_transform.a
    ys = win_transform.f + (rows + 0.5) * win_transform.e
    d = np.hypot(xs - centre.x, ys - centre.y).astype(np.float32)
    gr, gc = rows + r0, cols + c0
    better = d < best_dist[gr, gc]
    idx = (gr[better], gc[better])
    best_dist[idx] = d[better]
    owner[idx] = i

print(f"allocated cells: {int((owner > 0).sum()):,}")

# Persist the allocation so accessibility, risk and every later stage use the
# SAME zones. Recomputing it independently is how b03 silently disagreed with
# b02 before: it rasterised overlapping footprints instead.
alloc_profile = {"driver": "GTiff", "height": H, "width": W, "count": 1,
                 "dtype": "int32", "crs": CRS, "transform": transform,
                 "nodata": 0, "compress": "deflate"}
with rasterio.open("data/processed/allocation.tif", "w", **alloc_profile) as dst:
    dst.write(owner, 1)
    dst.update_tags(method="nearest place-node centre among containing footprints",
                    index_base="1-based row order of habitations.geojson")

# ---- zonal statistics on the allocation zone --------------------------------
with rasterio.open("data/processed/population.tif") as s:
    pop_grid = s.read(1)

n = len(hab)
flat = owner.ravel()
sv_all = susc.ravel()
pv_all = np.nan_to_num(pop_grid.ravel())
sel = (flat > 0) & np.isfinite(sv_all)
ids = flat[sel] - 1
sv, pv = sv_all[sel], pv_all[sel]

cells = np.bincount(ids, minlength=n)
sum_susc = np.bincount(ids, weights=sv, minlength=n)
max_susc = np.zeros(n)
np.maximum.at(max_susc, ids, sv)
high_cells = np.bincount(ids, weights=(sv >= HIGH_BREAK).astype(float), minlength=n)
sum_pop = np.bincount(ids, weights=pv, minlength=n)
exposed_pop = np.bincount(ids, weights=pv * (sv >= HIGH_BREAK), minlength=n)

with np.errstate(invalid="ignore", divide="ignore"):
    hab["mean_hazard"] = np.where(cells > 0, sum_susc / np.maximum(cells, 1), np.nan).round(1)
    hab["max_hazard"] = np.where(cells > 0, max_susc, np.nan).round(1)
    hab["exposed_area_percent"] = np.where(cells > 0, 100 * high_cells / np.maximum(cells, 1), np.nan).round(1)
hab["allocated_area_km2"] = (cells * CELL_AREA / 1e6).round(4)
hab["analysed_area_km2"] = hab["allocated_area_km2"]
hab["population"] = np.round(sum_pop).astype(int)
hab["exposed_population"] = np.round(exposed_pop).astype(int)
hab["cells"] = cells
# The allocation raster stores 1-based row indices of THIS frame. Any later
# stage that re-sorts (priority does) must carry this column, or raster zone i
# will be attributed to the wrong settlement.
hab["alloc_index"] = np.arange(1, len(hab) + 1)

before = len(hab)
hab = hab[hab["cells"] > 0].copy()
print(f"settlements with at least one allocated cell: {len(hab)} of {before}")

hab = hab.drop(columns=["cells", "centre"]).to_crs("EPSG:4326")
hab.to_file("data/processed/habitations.geojson", driver="GeoJSON")

# ---- district-wide exposure (distinct from settlement exposure) --------------
district_valid = np.isfinite(susc)
district_pop = float(np.nansum(np.where(district_valid, pop_grid, 0)))
district_exposed = float(np.nansum(np.where(district_valid & (susc >= HIGH_BREAK), pop_grid, 0)))
settlement_pop = int(hab["population"].sum())
settlement_exposed = int(hab["exposed_population"].sum())

summary = {
    "district": {
        "population": round(district_pop),
        "exposed_population": round(district_exposed),
        "exposed_share_percent": round(100 * district_exposed / max(district_pop, 1), 2),
        "note": "all GHSL population in the district, regardless of settlement footprint",
    },
    "settlements": {
        "count": len(hab),
        "population": settlement_pop,
        "exposed_population": settlement_exposed,
        "exposed_share_percent": round(100 * settlement_exposed / max(settlement_pop, 1), 2),
        "note": "population inside allocated settlement zones only; a subset of the district",
    },
    "allocation_method": "nearest place-node centre among containing footprints (Voronoi, clipped)",
    "hazard_break": HIGH_BREAK,
}
json.dump(summary, open("data/processed/exposure_summary.json", "w"), indent=1)

print(f"\nDISTRICT   population {round(district_pop):,}  exposed {round(district_exposed):,} "
      f"({summary['district']['exposed_share_percent']} %)")
print(f"SETTLEMENT population {settlement_pop:,}  exposed {settlement_exposed:,} "
      f"({summary['settlements']['exposed_share_percent']} %)")
print("  (settlement totals are a subset of district totals — never interchange them)")

top = hab.nlargest(10, "exposed_population")[
    ["name", "place", "population", "exposed_population", "exposed_area_percent",
     "mean_hazard", "footprint_source"]]
print("\ntop 10 settlements by exposed population:")
print(top.to_string(index=False))
print("\nwrote habitations.geojson, exposure_summary.json")
