# Methodology

The pipeline, end to end. Every stage is a script in `scripts/geospatial/`,
runnable in order, writing to `data/processed/`.

```
a01 boundary ──> a02 DEM ──> a03 terrain (slope, relief)
                                   │
        a04 rainfall ──────────────┤
                                   ▼
                          b01 susceptibility  ──> red zones (b05)
                                   │
        a05 population ────────────┤
        a06 OSM settlements ───────┤
                                   ▼
                            b02 exposure
                                   │
        a06 roads + health ──> b03 accessibility
                                   ▼
                             b04 risk engine  ──> priority (b05)
```

---

## 1. Terrain (`a03_terrain.py`)

DEM reprojected to **EPSG:32643, 30 m** before any derivative is computed.
Deriving slope on a geographic grid would treat one degree of longitude as one
degree of latitude and under-report east–west slope by roughly cos(latitude) —
about 15 % at 32 °N.

**Slope** — Horn (1981) 3×3 weighted difference, the method used by GDAL,
ArcGIS and QGIS. Derivatives are computed on the *unclipped* grid and clipped
afterwards, so district-edge cells have valid neighbours instead of NaN.

**Local relief** — 5×5 maximum minus minimum, a ruggedness proxy.

Observed: median slope 11.2°, p90 37.7°, 18.9 % of the district above 30°,
3.3 % above 45°.

## 2. Landslide susceptibility (`b01_susceptibility.py`)

A transparent weighted overlay of three normalised factors.

| Factor | Weight | Normalisation | Why |
|---|---|---|---|
| Slope | 0.45 | Piecewise, peaking at 35–45° | Dominant topographic control on shallow failure |
| Monsoon rainfall | 0.30 | Linear, 200–2,000 mm | Dominant trigger; spans a real 1,768 mm gradient inside the district |
| Local relief | 0.25 | Linear, 0–200 m, saturating | Slope length and terrain energy |

**The slope response is deliberately non-monotonic.** Susceptibility rises
through 15–35°, peaks at 35–45°, then *falls* above ~55° because very steep
faces are typically bare rock that has already shed its regolith. A linear
normalisation would rank cliff faces as the district's most dangerous ground,
which is wrong.

Breakpoints (degrees → 0–1): 0→0.00, 10→0.10, 20→0.45, 35→0.95, 45→1.00,
60→0.70, 90→0.35.

Classified on the specified breaks:

| Class | Range | Area | Share |
|---|---|---|---|
| Very Low | 0–20 | 1,130 km² | 19.8 % |
| Low | 20–40 | 2,571 km² | 45.1 % |
| Moderate | 40–60 | 1,063 km² | 18.6 % |
| High | 60–80 | 868 km² | 15.2 % |
| Very High | 80–100 | 73 km² | 1.3 % |

> The weights are **expert judgement from the literature, not calibrated**
> against observed landslides, because no inventory was obtainable. See
> `docs/limitations.md`.

## 3. Exposure (`b02_exposure.py`)

The step the prototype never had: hazard ∩ habitation ∩ population.

Settlement footprints come from OSM residential polygons where one contains the
place node (138 settlements), otherwise from a class-based circular buffer
(1,045 settlements: city 2,500 m, town 1,200 m, suburb 800 m, village 500 m,
hamlet 250 m). Every record carries `footprint_source` so the approximation is
visible downstream.

Footprints are rasterised to the 30 m grid and statistics accumulated with
`bincount`. Per settlement:

- `mean_hazard`, `max_hazard` — susceptibility over the footprint
- `exposed_area_percent` — share of footprint cells at susceptibility ≥ 60
- `population` — sum of the GHSL grid over the footprint
- `exposed_population` — population **in cells** at susceptibility ≥ 60, not a
  proportional estimate

District result: 577,244 residents inside settlement footprints, of whom
12,783 (2.2 %) are in High or Very High terrain.

## 4. Accessibility (`b03_accessibility.py`)

`site_slope_mean_deg`, `dist_to_road_m`, `dist_to_major_road_m`,
`dist_to_health_m` — all measured, none assigned. Distances are Euclidean;
see limitations.

## 5. Risk engine (`services/risk_engine/`)

```
HAZARD ─────┐
EXPOSURE ───┤
            ├──> weighted sum ──> risk 0-100 ──> classification
VULNERAB. ──┤
RESPONSE ───┘
```

| Component | Weight | Built from |
|---|---|---|
| Hazard | 0.35 | 0.75·mean_hazard + 0.25·max_hazard |
| Exposure | 0.30 | 0.5·exposed_area% (0–60 linear) + 0.5·exposed_population (log, cap 5,000) |
| Vulnerability | 0.20 | 0.6·site slope (piecewise) + 0.4·settlement-class service penalty |
| Response | 0.15 | 0.45·major-road distance + 0.35·health distance + 0.20·local-road distance |

Exposed population is **log-scaled**: counts span from 5 to ~1,400 people, and
a linear scale would make exposure a proxy for settlement size alone.

Classification: critical ≥ 75, high 60–75, monitor 40–60, safe < 40.

## 6. Explanation (`services/risk_engine/explanation.py`)

Each factor's contribution is exactly `component_score × component_weight`, and
the four sum to the risk score. This is a **transparent weighted contribution**
— an arithmetic decomposition of a linear model. It is auditable, but it is
**not SHAP**, and the interface must not call it SHAP unless a real
machine-learning model and explainer are introduced.

## 7. Red zones (`b05_redzones_priority.py`)

Susceptibility ≥ 60 → boolean mask → polygonised → polygons below 0.05 km²
dropped as raster noise → simplified at one cell (30 m). Result: **867 polygons,
881 km²**, largest contiguous zone 308 km². Each carries its mean
susceptibility so the map can shade by severity.

The red zone is now geometry derived from a surface, not a circle drawn where a
record said `level === 'critical'`.

## 8. Priority (`b05_redzones_priority.py`)

Risk asks *how dangerous*. Priority asks *where to act first*.

```
priority = 0.45·risk + 0.35·log(exposed_population) + 0.20·response_difficulty
```

This matters: the highest-*risk* settlements are tiny hamlets sitting entirely
inside hazardous ground, while the highest-*priority* settlements balance that
against how many people are exposed and how hard they are to reach.

Top of the priority list: **Upper Bara Bhanghal**, a hamlet reachable only on
foot over high passes — which the model ranked first without being told
anything about its reputation.

---

## 9. Candidate relocation sites (`c01_candidate_sites.py`)

The invented "Site A/B/C" are gone. Candidates are contiguous patches of Kangra
that survived a spatial screen on the 30 m grid.

**Screening funnel** (measured, in order):

| Step | Cells | Area |
|---|---|---|
| District | 6,338,007 | 5,704 km² |
| susceptibility < 40 | 4,111,770 | 3,701 km² |
| slope ≤ 15° | 3,759,505 | 3,384 km² |
| elevation ≤ 2,200 m | 3,642,583 | 3,278 km² |
| not already settled | 3,226,510 | 2,904 km² |

Surviving cells are grouped into 8-connected components; components below 5 ha
are dropped. Result: **405 candidates**, 342 FEASIBLE, 63 REVIEW.

Suitability = 0.40·safety + 0.25·terrain + 0.20·road access + 0.15·healthcare
access. Safety dominates because the point is to leave hazardous ground.

Status: FEASIBLE if suitability ≥ 60 **and** max susceptibility < 60;
REVIEW if suitability ≥ 45; otherwise REJECTED.

## 10. Carrying capacity (`c02_capacity.py`)

```
effective = MIN(land, infrastructure, healthcare, environmental, accessibility)
available = MAX(0, effective − current_population)
binding   = whichever produced the minimum
```

| Constraint | How | Status |
|---|---|---|
| Land | developable hectares measured from the slope raster (≤10° full, 10–15° half) × 100 persons/ha | DERIVED + curated density |
| Environmental | water availability proxy (not a measured yield): annual rainfall × area × runoff 0.15, ÷ 55 lpcd (Jal Jeevan Mission norm) | DERIVED + curated runoff |
| Healthcare | OSM facilities within 10 km × IPHS hill norms (hospital 30k, PHC 20k, sub-centre 3k) minus existing population load | DERIVED |
| Infrastructure | documented ceiling scaled by measured distance to a major road | CURATED_PILOT_ASSUMPTION |
| Accessibility | documented ceiling scaled by measured distance to any road | CURATED_PILOT_ASSUMPTION |

Observed binding constraints across 405 candidates: land 338, healthcare 43,
infrastructure 24. Every constraint carries its derivation string in the API.

## 11. Constrained optimisation (`services/optimization_engine/`)

OR-Tools MIP (CBC). Greedy first-fit is gone.

```
variables    x[i][j] people moved from habitation i to site j (integer)
             u[i]    people left unallocated (slack)
demand       Σ_j x[i][j] + u[i] = exposed_population_i
capacity     Σ_i x[i][j] ≤ available_capacity_j
safety       x[i][j] = 0 unless site j screened FEASIBLE
accessibility x[i][j] = 0 beyond max_distance_km (default 40)
minimise     Σ x[i][j]·(distance_km + (100 − suitability_j)/10) + 1000·Σ u[i]
```

The slack term is deliberate: without it, one unreachable habitation makes the
whole model INFEASIBLE and the operator learns nothing. With it the solver
still returns an optimal assignment and reports exactly who could not be placed.

Baseline result: **OPTIMAL**, 67 source habitations, 309 eligible sites,
2,480 people allocated across 68 assignments to 21 sites, 0 unallocated,
distances 0.4–4.3 km. The status shown in the UI is the solver's own status —
"optimal" is never asserted when the solver did not return OPTIMAL.

## 12. Scenario propagation (`services/scenario_engine/`)

A scenario re-runs the chain in-process (~0.5–2 s), it does not adjust numbers:

```
rainfall/population/roads → susceptibility raster → settlement exposure
→ risk → priority → candidate re-screening → capacity → optimisation
```

| Control | Propagates by | Honest? |
|---|---|---|
| Rainfall ±% | scales the rainfall raster, a real susceptibility input | genuine |
| Population ±% | scales the GHSL grid, changing exposure and demand | genuine |
| Road availability % | inflates effective distance (`×100/availability`) | **documented transformation, not a network model** |

Fixed and stated: slope, relief, elevation and facility locations do not
respond. Nothing models landslide *occurrence*.

Measured propagation (baseline → rainfall +50%, roads 60%):

| | Baseline | Scenario |
|---|---|---|
| Critical settlements | 0 | 6 |
| High-risk settlements | 69 | 112 |
| Exposed population | 12,780 | 21,703 |
| Feasible sites | 342 | 33 |
| Available capacity | 586,706 | 120,532 |

`tests/test_consistency.py` asserts that a zero-delta scenario reproduces the
stored pipeline exactly, so the scenario panel can never contradict the map.

## 13. API and frontend

```
React → IntelligenceProvider (src/data/provider.ts) → FastAPI → engines → data/processed
```

The browser computes no analytical value. `src/data/mock.ts` is no longer
authoritative: it is a development fixture used only when the API is
unreachable, and the console displays a **DEVELOPMENT FIXTURE** banner when
that happens, so invented numbers can never masquerade as analysis.

## 14. Verification

| Check | File | Asserts |
|---|---|---|
| Allocation determinism | `tests/test_allocation_order.py` | identical cell/population allocation across original, shuffled and reversed input order for all 1,183 settlements |
| Engine consistency | `tests/test_consistency.py` | a zero-delta scenario reproduces the stored pipeline exactly; rainfall increases exposure and never creates safer sites |
| API contract | `tests/test_api_contract.py` | the same entity carries the same numbers through exposure → risk → capacity → optimisation → brief; zero-delta scenario is a no-op; solver status is one of the real enum values |
| Traceability | `scripts/geospatial/verify_trace.py <name>` | re-derives mean/max hazard, exposed area, population, exposed population and site slope directly from the rasters and compares against the stored record |
| DEM quality | `scripts/geospatial/qa01_dem.py` | separates buffer overhang from true interior voids — result: 3,380 cells overhang the district edge, **0** true voids, no in-district analysis affected |

Frontend: `npx tsc -b` and `npm run build` both pass. The decision loop was
driven end to end in a real browser, and the demo was re-run with the basemap
blocked, the API blocked, and all external hosts blocked.


## Hazard-specific risk

Every risk figure is a risk **of a named hazard**. The API attaches
`hazard_type` and the hazard model to each settlement, and the UI builds its
label from it, so no screen can show a bare "risk index". In the Kangra pilot
the only registered model is landslide:

| | |
|---|---|
| Label | Landslide risk index, 0-100 |
| Hazard basis | slope 0.45, monsoon rainfall 0.30, local relief 0.25 (weights of the susceptibility index — not accuracy, not probability) |
| Hazard component | 0.75 × mean susceptibility + 0.25 × peak susceptibility |
| Risk | 0.35 hazard + 0.30 exposure + 0.20 vulnerability (proxy) + 0.15 response difficulty (proxy) |
| Meaning | decision-support index; **not** the probability of a landslide |

Why a settlement's risk differs from its susceptibility: susceptibility is the
physical hazard alone; risk also weighs who is exposed, how vulnerable the site
is, and how hard it is to reach. Kharandar: mean susceptibility 60.1, risk 69.6
(66.9×0.35 + 66.4×0.30 + 75.9×0.20 + 74.0×0.15), displayed as 70.

**Other hazards are not implemented.** Earthquake, flood and cyclone appear in
the type system only. None is registered in the API, and none may reuse the
landslide formula: each requires its own hazard layer (ground shaking, flood
depth, wind field) and its own exposure and vulnerability terms before any
score for it can be shown.
