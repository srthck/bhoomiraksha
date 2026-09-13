# Data Sources

Every dataset used by the Bhoomi Raksha analytical pipeline. Acquisition is
reproducible: each row names the script that fetches and processes it.

Study area: **Kangra district, Himachal Pradesh** — 5,704 km², bbox
75.5788–77.0642 °E, 31.6887–32.4723 °N.
Analysis grid: **EPSG:32643 (UTM 43N), 30 m**, 4651 × 2925, 6,338,007 cells.

---

## 1. Administrative boundary

| Field | Value |
|---|---|
| Dataset | India district boundaries |
| Source | `geohacker/india` (open mirror of GADM administrative units) |
| URL | https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson |
| Licence | Open data mirror; GADM is free for academic and non-commercial use |
| Acquired | 2026-09-10 |
| Spatial resolution | Vector, generalised |
| Temporal coverage | GADM 2.x vintage administrative units |
| Processing | Selected `NAME_2 = "Kangra"`, `NAME_1 = "Himachal Pradesh"`; written to `kangra_boundary.geojson` |
| Script | `scripts/geospatial/a01_boundary.py` |
| Validation | Computed area 5,704 km² vs published ~5,739 km² (−0.6 %) |
| **Limitations** | **Not an official Survey of India boundary.** Generalised; unsuitable for legal or cadastral use. District boundaries in India have changed since the GADM vintage. |

## 2. Elevation

| Field | Value |
|---|---|
| Dataset | AWS Terrain Tiles (Mapzen), terrarium encoding, zoom 12 |
| Source | Amazon Web Services Open Data |
| URL | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` |
| Licence | Public domain / CC-BY depending on contributing source; over India the source is SRTM (public domain, NASA/USGS) |
| Acquired | 2026-09-10 |
| Spatial resolution | ~26 m/px at 32°N (zoom 12); underlying SRTM is 1 arc-second (~30 m) |
| Temporal coverage | SRTM acquisition 2000, with later void fills |
| Processing | 247 tiles mosaicked → EPSG:32643 @ 30 m (bilinear) → values outside 100–7,000 m masked (2.61 %) → clipped to district |
| Script | `scripts/geospatial/a02_dem.py`, `a03_terrain.py` |
| Validation | Max elevation 5,981 m vs Hanuman Tibba 5,982 m; median 737 m consistent with the Kangra valley |
| **Limitations** | SRTM is a surface model, so tree canopy and buildings are included. Steep-terrain voids are interpolated by the tile provider. |

## 3. Rainfall

| Field | Value |
|---|---|
| Dataset | WorldClim 2.1 monthly precipitation |
| Source | WorldClim / UC Davis |
| URL | https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_prec.zip |
| Licence | CC BY-SA 4.0 |
| Citation | Fick, S.E. & Hijmans, R.J. (2017), *International Journal of Climatology* 37(12):4302–4315 |
| Acquired | 2026-09-10 |
| Spatial resolution | 2.5 arc-minutes (~4.6 km) |
| Temporal coverage | 1970–2000 climatological normals |
| Processing | Jun–Sep months summed → monsoon total → bilinear resample onto the 30 m grid |
| Script | `scripts/geospatial/a04_rainfall.py` |
| Validation | District range 215–1,983 mm; the ~1,983 mm maximum matches Dharamshala's monsoon, the 215 mm minimum the trans-Dhauladhar rain shadow |
| **Limitations** | ~4.6 km cells give roughly 28 × 19 samples across the district — resolves the orographic gradient, **not** hillslope detail. Resampling to 30 m interpolates, it does not add information. A 30-year normal, not current-season or event rainfall. |

## 4. Population

| Field | Value |
|---|---|
| Dataset | GHSL GHS-POP R2023A, epoch 2020, 100 m |
| Source | European Commission Joint Research Centre |
| URL | JRC JEODPP, tiles `R6_C25`, `R6_C26` |
| Licence | CC BY 4.0 |
| Acquired | 2026-09-10 |
| Spatial resolution | 100 m, Mollweide (ESRI:54009) |
| Temporal coverage | Modelled to epoch 2020 |
| Processing | Two tiles mosaicked → counts converted to density → reprojected (average) to the 30 m grid → multiplied by cell area, preserving totals |
| Script | `scripts/geospatial/a05_population.py` |
| Validation | District total 1,652,806 vs Census 2011 1,510,075 (+9.5 %, consistent with ~9 years of growth) |
| **Limitations** | **A modelled grid, not a census.** Population is redistributed from coarser census units using built-up surface, so per-settlement figures are estimates. Village-level Census 2011 counts are not openly available in machine-readable form. |

## 5. Settlements, roads, health facilities

| Field | Value |
|---|---|
| Dataset | OpenStreetMap — `place` nodes, `highway` ways, health `amenity`/`healthcare` features, `landuse=residential` polygons |
| Source | Overpass API |
| Licence | **ODbL 1.0 — "© OpenStreetMap contributors" attribution is required wherever this is displayed** |
| Acquired | 2026-09-10 |
| Spatial resolution | Vector, contributor-dependent |
| Temporal coverage | Live database snapshot |
| Processing | Bounding-box query → clipped to district → settlement footprints built from residential polygons where available, else class-based buffers |
| Script | `scripts/geospatial/a06_osm.py`, `b02_exposure.py` |
| Counts | 1,183 place nodes (1,151 analysed), 5,557 road segments / 5,959 km, 209 health facilities, 1,164 residential polygons |
| **Limitations** | OSM completeness in rural Himachal is uneven. Only 138 of 1,151 settlements had a usable polygon — the other 1,045 use **approximated circular footprints**, flagged per record as `footprint_source = "buffer_approx"`. Only 25 place nodes carry a population tag, so population comes from GHSL instead. Health-facility coverage is incomplete, so distance-to-care is a lower bound on true remoteness. |

---

## 6. Datasets sought but NOT obtained

| Dataset | Why it matters | What was tried | Consequence |
|---|---|---|---|
| Historical landslide inventory | Weighting **and** validation of the susceptibility model | NASA Global Landslide Catalog / COOLR via `data.nasa.gov`, the LHASA repository and two ArcGIS feature services — all returned 404/400/500. GSI's inventory is not openly downloadable. | The susceptibility model is **uncalibrated and unvalidated**. No AUC, hit rate or confusion matrix can be reported. |
| Village-level Census 2011 | Authoritative population per settlement | Not openly available in machine-readable form | Population is a modelled GHSL estimate |
| SECC / socio-economic indicators | Genuine social vulnerability | Not openly available per settlement | "Vulnerability" is explicitly a terrain-and-service proxy, not social vulnerability |
| Road network routing / travel time | Real accessibility | Requires a routing engine over the OSM graph | Accessibility uses **Euclidean** distance, which understates travel distance in mountains |

---

## 7. Assets that are NOT data

These are renders used by the interface. They must never be used as analytical
inputs — see `docs/data-inventory.md` §1.2.

`public/geo/pilot-relief.jpg`, `india-hero.png`, `india-context-wide.jpg`,
`clouds.png`, `public/geo/earth/**` (NASA Blue Marble, public domain),
`src/geo/indiaGeometry.ts`.
