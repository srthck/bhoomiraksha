# Bhoomi Raksha — Data Inventory

**Date of inventory:** 2026-09-10
**Pilot study area:** Kangra district, Himachal Pradesh, India

This document is the honest starting position before the intelligence layer was
built. It answers four questions for every asset already in the repository:
is it real, is it synthetic, is it visual-only, and is it analytically usable?

The distinction that matters most: **a hillshaded JPEG is a picture of terrain,
not terrain.** Several assets in this project look geographic but carry no
recoverable elevation, and must never be fed to an analytical step.

---

## 1. What was already in the repository

### 1.1 Analytically usable (real measurement data)

| Asset | What it is | Source | Usable for |
|---|---|---|---|
| `scripts/.cache/tiles10/` (255 PNG tiles) | Terrarium-encoded elevation, zoom 10, covering 74–79°E / 29.8–34.5°N | AWS Terrain Tiles (Mapzen), built from SRTM/ASTER/NED | Elevation, slope — but ~130 m/px at this latitude, coarser than the SRTM 30 m source |
| `scripts/.cache/` z6 tiles | Same encoding, zoom 6, subcontinental | AWS Terrain Tiles | Landing visuals only; far too coarse for analysis |

Terrarium tiles are a genuine elevation product: each pixel decodes to metres
via `(R*256 + G + B/256) - 32768`. This is the **only** real analytical raster
the project had before this work.

### 1.2 Visual-only (no analytical value)

These are renders. They encode colour, not measurement. None may be used as an
input to hazard, slope, or exposure calculations.

| Asset | Size | Why it is not data |
|---|---|---|
| `public/geo/pilot-relief.jpg` | 1.2 MB, 2048×2321 | Hillshaded + hypsometrically tinted JPEG. Elevation is destroyed by the colour ramp, the shading and JPEG compression. Explicitly **not** a DEM. |
| `public/geo/india-hero.png` | 688 KB | Masked relief render of India for the landing hero |
| `public/geo/india-context-wide.jpg` | 348 KB | Wider relief backdrop for the landing |
| `public/geo/earth/**` (85 JPEG tiles) | 710 KB | NASA Blue Marble reprojected to Web Mercator, z0–z3, for the globe phase |
| `public/geo/clouds.png` | 213 KB | Procedural fractal-noise cloud sheet. Not meteorological data. |
| `src/geo/indiaGeometry.ts` | 78 KB | India state outlines pre-projected to **pixel** coordinates for the landing SVG. Geographic information is present but baked to one raster's frame; not a usable geometry layer. |

### 1.3 Synthetic / curated demo data

Everything the product currently reasons about is invented. This is the gap the
rebuild closes.

| Asset | Content | Status |
|---|---|---|
| `src/data/mock.ts` → `region` | `Kangra Pilot Region`, `HP-04`, critical 12, high-risk 27, exposed 18,420 | **Invented.** No calculation produced these. |
| `src/data/mock.ts` → `habitations` | Village A–D at real Kangra coordinates, with risk 87/73/61/44 and populations 4,830/2,140/1,220/980 | **Coordinates are plausible and inside Kangra; every attribute is invented.** Village names are placeholders, not real settlements. |
| `src/data/mock.ts` → `factors` | Contribution values (+25, +22, +18, …) shown in the WHY panel | **Invented.** Hand-authored to look like an explanation. Not model output, and specifically **not SHAP**. |
| `src/data/mock.ts` → `sites` | Site A–C with safety/healthcare/accessibility/infrastructure scores and five-way capacity profiles | **Invented.** Not derived from any spatial screening. |
| `calculateScenario()` | Rainfall/roads/population sliders → deterministic arithmetic | Real arithmetic over invented inputs; propagates nothing spatial. |
| `calculateOptimization()` | Greedy first-fit allocation | Real greedy algorithm, but **not** constrained optimisation. The UI must not call this "optimal" without qualification. |

### 1.4 Live services the running app depends on

| Service | Used for | Analytical? |
|---|---|---|
| `tiles.openfreemap.org` (Liberty style) | Roads, water, labels on the console basemap | Cartographic only — consumed as rendered vector tiles, not queried |
| `s3.amazonaws.com/elevation-tiles-prod` (raster-dem) | MapLibre hillshade at z≥7 | Real elevation, but used for **display** shading only |

---

## 2. What is missing

| Dataset | Needed for | Status after this inventory |
|---|---|---|
| Kangra district boundary | Study area / clipping | **Acquired** — see §3 |
| DEM at native resolution | Slope, relief, susceptibility | **To acquire** — z10 cache is too coarse; need z12 (~32 m) |
| Rainfall | Susceptibility triggering factor | **To acquire** — CHIRPS reachable |
| Historical landslide inventory | Model weighting *and* validation | **NOT AVAILABLE** — see §4 |
| Habitation geometry | Exposure | **To acquire** — OpenStreetMap |
| Population | Exposed population | **To acquire** — GHSL 100 m |
| Roads | Accessibility / response difficulty | **To acquire** — OpenStreetMap |
| Health facilities | Response difficulty, site screening | **To acquire** — OpenStreetMap |
| Candidate relocation areas | Site screening | **To derive** — from terrain + hazard + access screening, clearly labelled as derived |

---

## 3. Acquired during this work

| Dataset | File | Validation |
|---|---|---|
| Kangra district boundary | `data/processed/kangra_boundary.geojson` | Computed area **5,704 km²** against a published district area of ~5,739 km² (−0.6 %, consistent with boundary generalisation) |

Study-area bounding box: **75.5788 – 77.0642 °E, 31.6887 – 32.4723 °N**

---

## 4. Known gaps and how they are handled

**Historical landslide inventory — unavailable.**
The NASA Global Landslide Catalog / COOLR endpoints tested (`data.nasa.gov`,
the LHASA repository, and two ArcGIS feature services) all returned 404/400/500.
The Geological Survey of India landslide inventory is not openly downloadable.

Consequences, stated plainly:

1. The susceptibility model in this pilot is **terrain- and rainfall-driven
   only**. It has no historical-evidence factor.
2. It is therefore **unvalidated**. No AUC, no hit rate, no confusion matrix can
   be reported, because there is no ground truth to test against.
3. The product must describe it as a *susceptibility index*, never as a
   *validated landslide prediction*.

**Population is modelled, not censused.** GHSL is a globally modelled population
grid, not the Indian Census. Village-level Census 2011 figures are not openly
downloadable in machine-readable form. Population figures must be labelled as
gridded estimates.

**Administrative boundary provenance.** The district boundary comes from an open
third-party mirror of GADM, not from an official Survey of India release. It is
adequate for a pilot study area; it is not an authoritative boundary.

**Village names.** "Village A–D" are placeholders. Where the rebuild attaches
real OpenStreetMap settlements, those carry real names; where it retains the
demo entities, they stay clearly labelled as demo.

---

## 5. Rules adopted from this inventory

1. Never use `pilot-relief.jpg` or any `public/geo/*` render as an analytical input.
2. Never describe the WHY panel as SHAP until an actual ML model with an
   explainer exists. Call it a transparent weighted contribution.
3. Never attribute a dataset to a government source it did not come from.
4. Every number the UI shows must be traceable to a file in `data/processed/`
   and a documented calculation, or be labelled demo data.
5. Where a dataset is unavailable, the limitation is written into
   `docs/limitations.md` and surfaced in the product, not hidden.
