"""Acquire the Kangra district boundary — the study area every other layer clips to.

Source: geohacker/india district boundaries (derived from GADM / Survey of India
administrative units). This is a third-party open mirror, NOT an official
Survey of India release; see docs/data-sources.md for the limitation note.
"""
import json
import os
import urllib.request

import geopandas as gpd

SRC = "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson"
RAW = "data/raw/india_district.geojson"
OUT = "data/processed/kangra_boundary.geojson"

os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

if not os.path.exists(RAW):
    print("downloading district boundaries…")
    urllib.request.urlretrieve(SRC, RAW)
print(f"raw: {os.path.getsize(RAW) / 1e6:.1f} MB")

gdf = gpd.read_file(RAW)
print("columns:", list(gdf.columns))

# find Kangra in Himachal Pradesh
name_cols = [c for c in gdf.columns if gdf[c].dtype == object]
hits = gdf[gdf.apply(lambda r: any(str(r[c]).strip().lower() == "kangra" for c in name_cols), axis=1)]
print(f"matches for 'Kangra': {len(hits)}")
print(hits[[c for c in name_cols if c in hits.columns]].to_string())

kangra = hits.copy()
kangra = kangra.set_crs("EPSG:4326", allow_override=True)
kangra.to_file(OUT, driver="GeoJSON")

b = kangra.total_bounds
area_km2 = kangra.to_crs("EPSG:32643").area.sum() / 1e6
print(f"\nbbox  west={b[0]:.5f} south={b[1]:.5f} east={b[2]:.5f} north={b[3]:.5f}")
print(f"area  {area_km2:.0f} km2   (published Kangra district area is ~5,739 km2)")
print(f"wrote {OUT}")
json.dump({"west": b[0], "south": b[1], "east": b[2], "north": b[3], "area_km2": area_km2},
          open("data/processed/kangra_bbox.json", "w"), indent=1)
