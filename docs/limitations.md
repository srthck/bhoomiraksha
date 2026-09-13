# Limitations

What this system does not know, stated plainly. If a judge, reviewer or
official asks any of these questions, the honest answer is here.

---

## 1. The hazard model is unvalidated

**No landslide inventory for Kangra could be obtained.** NASA's Global Landslide
Catalog / COOLR endpoints, the LHASA repository and two ArcGIS feature services
all failed; the Geological Survey of India inventory is not openly downloadable.

Consequences:

- The factor weights (slope 0.45, rainfall 0.30, relief 0.25) are **expert
  judgement from the literature, not fitted to observed failures**.
- **No skill metric exists.** No AUC, no success-rate curve, no confusion
  matrix, no hit rate. Anyone asking "how accurate is it?" must be told: unknown.
- The output is a **susceptibility index** — a relative ranking of predisposition
  — not a probability, a forecast, or a prediction of when or whether a slope
  will fail.

This is the single most important limitation in the project.

## 2. "Vulnerability" is not social vulnerability

Socio-economic data per settlement (housing type, income, age structure, SECC)
is not openly available. The vulnerability term is built from mean site slope
and settlement class, and is therefore a **terrain-and-service proxy**. It says
nothing about who lives there or how well they could cope.

## 3. Population is modelled, not counted

GHSL redistributes coarser census figures using built-up surface. Per-settlement
population is an **estimate**, not a census count. The district total
(1,652,806) validates well against Census 2011 (1,510,075, +9.5 % over ~9 years),
but that agreement at district level does not guarantee accuracy for any
individual hamlet.

## 4. Most settlement footprints are approximated

Only **138 of 1,151** settlements had a usable OSM polygon. The other **1,045**
use a circular buffer sized by settlement class. Exposed-area percentages for
those settlements describe a circle, not the real built extent. Every record
carries `footprint_source`, and confidence is reduced by 0.20 when it is
`buffer_approx`.

## 4b. Overlapping settlement footprints — FIXED

Previously, footprints were rasterised into one zone grid and each shared cell
went to whichever settlement was rasterised last, so per-settlement population
depended on input order.

Cells are now allocated to the settlement whose place-node centre is nearest,
among those whose footprint contains the cell — a Voronoi partition clipped to
the footprints. It is deterministic, order-independent and cannot double-count.
`tests/test_allocation_order.py` asserts identical results across original,
shuffled and reversed input order for all 1,183 settlements.

The allocation is written to `data/processed/allocation.tif` and every later
stage reads it, so accessibility, risk and scenarios all use the same zones.
Original footprint geometry is preserved; `allocated_area_km2` sits alongside
`footprint_area_km2` so the difference is visible.

## 5. Accessibility is straight-line, not travel time

`dist_to_road_m`, `dist_to_major_road_m` and `dist_to_health_m` are Euclidean.
In Kangra's terrain the real journey can be several times the straight line —
Upper Bara Bhanghal is a multi-day walk from a road that is not far away on a
map. Response difficulty is therefore **understated** for the most remote
settlements. Network routing over the OSM graph is the correct fix and is not
implemented.

## 6. Rainfall resolution is coarse

WorldClim 2.5 arc-minute cells are ~4.6 km, giving roughly 28 × 19 samples
across the district. This resolves the range-scale orographic gradient but not
hillslope variation. Resampling to 30 m interpolates; it does not add
information. It is also a **1970–2000 climatological normal**, so it represents
the long-run monsoon regime, not any current or forecast season.

## 7. The DEM is a surface model

SRTM includes tree canopy and buildings. Slope in forested terrain is slightly
noisy as a result. Steep-terrain voids were interpolated by the tile provider;
2.61 % of cells fell outside the plausible 100–7,000 m range and were masked.

## 8. The administrative boundary is not official

Sourced from an open mirror of GADM, not Survey of India. Generalised, of
uncertain vintage, and unsuitable for legal, cadastral or notification use.

## 9. No settlement classifies as "critical" at baseline

Under baseline conditions the highest risk score in Kangra is **72.8**, below
the 75 threshold, so the district has 0 critical and 69 high-risk settlements.
This is reported as found; thresholds were **not** tuned to manufacture a
critical case.

Settlements do cross into critical under adverse scenarios: at rainfall +50%
with road availability at 60%, six settlements become critical and Kharandar
moves from 69.6 to 76.1. That transition is computed, not scripted.

## 10. What is still approximate in the relocation chain

Candidate screening, carrying capacity, constrained optimisation, scenario
propagation and the FastAPI layer are all implemented and wired to the UI. What
remains approximate:

- **No land ownership or land-use data.** Candidate patches are screened on
  terrain, hazard, occupation and watercourses only. A patch may be farmland,
  forest or private land; the pipeline cannot tell. Total candidate area
  (2,869 km²) is therefore an upper bound on what is genuinely available.
- **No protected-area or forest-cover layer.** The only environmental exclusion
  is a 30 m watercourse buffer.
- **Two capacity ceilings are curated.** Infrastructure and accessibility
  capacity use documented pilot ceilings scaled by measured road distance,
  because no electricity or piped-network dataset was available. They are
  labelled `CURATED_PILOT_ASSUMPTION` in the API response. Land, environmental
  (water availability proxy) and healthcare capacity are derived from real rasters and
  mapped facilities.
- **Road availability does not remove network links.** With no routing graph,
  reduced availability is modelled as inflated effective distance. This is
  stated in every scenario response under `propagation_notes`.
- **The optimiser minimises distance and site quality only.** It does not model
  construction cost, land acquisition, livelihood disruption or community
  preference.

## 11. Attribution obligations

OpenStreetMap data is ODbL 1.0. Any deployed interface showing settlements,
roads or health facilities **must** display "© OpenStreetMap contributors".
GHSL is CC BY 4.0 (European Commission JRC). WorldClim is CC BY-SA 4.0 and
should cite Fick & Hijmans (2017).
