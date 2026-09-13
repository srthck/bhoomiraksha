"""Settlements, roads and health facilities for Kangra, from OpenStreetMap.

Source: Overpass API. Licence: ODbL 1.0 — attribution to OpenStreetMap
contributors is required wherever this is displayed.

These are the first *real, named* settlements in the project. Everything the
prototype showed before ("Village A".."Village D") was invented.

OSM completeness in rural Himachal is uneven: the road network and place nodes
are good, health facilities are patchy, and population tags on place nodes are
rare. Those limits are recorded in docs/limitations.md rather than papered over.

Outputs (EPSG:4326, clipped to the district):
  data/processed/settlements.geojson
  data/processed/roads.geojson
  data/processed/health_facilities.geojson
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import geopandas as gpd
from shapely.geometry import LineString, Point

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
bbox = json.load(open("data/processed/kangra_bbox.json"))
BB = f"{bbox['south']:.5f},{bbox['west']:.5f},{bbox['north']:.5f},{bbox['east']:.5f}"

QUERIES = {
    "settlements": f"""[out:json][timeout:180];
        node["place"~"^(city|town|village|hamlet|suburb)$"]({BB});
        out body;""",
    "roads": f"""[out:json][timeout:300];
        way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential)$"]({BB});
        out geom;""",
    "health": f"""[out:json][timeout:180];
        (
          node["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]({BB});
          way["amenity"~"^(hospital|clinic|doctors)$"]({BB});
          node["healthcare"]({BB});
        );
        out center;""",
}


def overpass(query, name):
    raw = f"data/raw/osm_{name}.json"
    if os.path.exists(raw) and os.path.getsize(raw) > 100:
        print(f"  {name}: cached")
        return json.load(open(raw, encoding="utf-8"))
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep, data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": "bhoomi-raksha-pilot/1.0 (research)"},
                )
                with urllib.request.urlopen(req, timeout=300) as r:
                    payload = json.loads(r.read().decode())
                os.makedirs("data/raw", exist_ok=True)
                json.dump(payload, open(raw, "w", encoding="utf-8"))
                print(f"  {name}: {len(payload.get('elements', []))} elements from {ep.split('/')[2]}")
                return payload
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                print(f"  {name}: {ep.split('/')[2]} attempt {attempt + 1} failed ({e}); retrying")
                time.sleep(6)
    raise SystemExit(f"Overpass unreachable for {name}")


boundary = gpd.read_file("data/processed/kangra_boundary.geojson")
geom = boundary.union_all() if hasattr(boundary, "union_all") else boundary.unary_union

print("querying Overpass…")

# ---- settlements -------------------------------------------------------------
data = overpass(QUERIES["settlements"], "settlements")
rows = []
for el in data["elements"]:
    t = el.get("tags", {})
    rows.append({
        "osm_id": el["id"],
        "name": t.get("name") or t.get("name:en") or f"unnamed_{el['id']}",
        "place": t.get("place"),
        "osm_population": int(t["population"]) if str(t.get("population", "")).isdigit() else None,
        "geometry": Point(el["lon"], el["lat"]),
    })
settlements = gpd.GeoDataFrame(rows, crs="EPSG:4326")
settlements = settlements[settlements.within(geom)].reset_index(drop=True)
settlements.to_file("data/processed/settlements.geojson", driver="GeoJSON")
print(f"\nsettlements in district: {len(settlements)}")
print(settlements["place"].value_counts().to_string())
print(f"  with an OSM population tag: {settlements['osm_population'].notna().sum()}")

# ---- roads -------------------------------------------------------------------
data = overpass(QUERIES["roads"], "roads")
rows = []
for el in data["elements"]:
    pts = [(p["lon"], p["lat"]) for p in el.get("geometry", []) if p]
    if len(pts) < 2:
        continue
    t = el.get("tags", {})
    rows.append({"osm_id": el["id"], "highway": t.get("highway"),
                 "name": t.get("name"), "surface": t.get("surface"),
                 "geometry": LineString(pts)})
roads = gpd.GeoDataFrame(rows, crs="EPSG:4326")
roads = gpd.clip(roads, geom).reset_index(drop=True)
roads = roads[roads.geometry.type.isin(["LineString", "MultiLineString"])]
roads.to_file("data/processed/roads.geojson", driver="GeoJSON")
km = roads.to_crs("EPSG:32643").length.sum() / 1000
print(f"\nroads in district: {len(roads)} segments, {km:,.0f} km")
print(roads["highway"].value_counts().to_string())

# ---- health facilities -------------------------------------------------------
data = overpass(QUERIES["health"], "health")
rows, seen = [], set()
for el in data["elements"]:
    t = el.get("tags", {})
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    if lon is None or lat is None:
        continue
    key = (round(lon, 6), round(lat, 6))
    if key in seen:
        continue
    seen.add(key)
    rows.append({"osm_id": el["id"],
                 "name": t.get("name") or "unnamed",
                 "kind": t.get("amenity") or t.get("healthcare"),
                 "geometry": Point(lon, lat)})
health = gpd.GeoDataFrame(rows, crs="EPSG:4326")
health = health[health.within(geom)].reset_index(drop=True)
health.to_file("data/processed/health_facilities.geojson", driver="GeoJSON")
print(f"\nhealth facilities in district: {len(health)}")
print(health["kind"].value_counts().to_string())
