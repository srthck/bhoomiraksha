import { distance } from '@turf/distance'
import { point } from '@turf/helpers'
import {
  api,
  type ApiHabitation,
  type ApiHabitationDetail,
  type ApiRegion,
  type ApiHazardModel,
  type ApiSite,
  type Confidence,
  type HazardType,
} from './api'
import {
  calculateOptimization,
  calculateScenario,
  habitations as mockHabitations,
  region as mockRegion,
  sites as mockSites,
  type Habitation,
  type RelocationSite,
  type RiskFactor,
  type ScenarioParameters,
} from './mock'

/* =========================================================================
   IntelligenceProvider — the boundary between the frozen UI and the analysis.

   The analytical path is: React -> this provider -> FastAPI -> engines ->
   processed Kangra data. `mock.ts` is NOT authoritative any more; it is a
   development fixture used only when the API cannot be reached, and when that
   happens the console says so rather than passing invented numbers off as
   analysis.
   ========================================================================= */

export type DataMode = 'analytical' | 'fallback'

export type RegionSummary = {
  /** Every risk figure in the console is a risk OF this hazard. */
  hazardType: HazardType
  /** Null only in development-fixture mode, where no model ran. */
  hazardModel: ApiHazardModel | null
  name: string
  code: string
  state: string
  primaryHazard: string
  areaKm2: number
  settlements: number
  districtPopulation: number
  districtExposed: number
  settlementPopulation: number
  settlementExposed: number
  critical: number
  high: number
  redZoneAreaKm2: number
  candidateSites: number
  feasibleSites: number
  updatedAt: string
  modelVersion: string
  disclaimer: string
  provenance: ApiRegion['provenance']
}

/** A settlement in the shape the existing panels already render. */
export type ConsoleHabitation = Habitation & {
  exposedPopulation: number
  exposedAreaPercent: number
  meanHazard: number
  maxHazard: number
  priorityRank: number
  priorityScore: number
  confidence: Confidence
  hazardType: HazardType
  detail?: ApiHabitationDetail
}

export type ConsoleSite = RelocationSite & {
  suitability: number
  screeningStatus: string
  bindingConstraint: string
  meanSusceptibility: number
  distanceKm: number | null
  constraints: ApiSite['constraints']
  areaKm2: number
  effectiveCapacity: number
  availableCapacity: number
}

const band = (v: number, bands: [number, string][]) => {
  for (const [limit, label] of bands) if (v < limit) return label
  return bands[bands.length - 1][1]
}

const hazardLabel = (v: number) => band(v, [[20, 'Very low'], [40, 'Low'], [60, 'Moderate'], [80, 'High'], [Infinity, 'Very high']])
const scoreLabel = (v: number) => band(v, [[25, 'Low'], [50, 'Moderate'], [75, 'High'], [Infinity, 'Very high']])
const accessLabel = (v: number) => band(v, [[25, 'Good'], [50, 'Moderate'], [75, 'Poor'], [Infinity, 'Very poor']])

function toHabitation(h: ApiHabitation, detail?: ApiHabitationDetail): ConsoleHabitation {
  const comp = detail?.components ?? {}
  const factors: RiskFactor[] = (detail?.explanation.contributions ?? []).map((c) => ({
    id: c.id,
    label: c.label,
    value: c.contribution,
    evidence: c.evidence,
  }))
  return {
    id: h.id,
    name: h.name,
    district: h.place ? `${h.place[0].toUpperCase()}${h.place.slice(1)} · Kangra` : 'Kangra',
    coordinates: [h.lon, h.lat],
    risk: h.risk_score,
    level: h.level,
    population: h.population,
    hazardExposure: hazardLabel(h.mean_hazard ?? 0),
    vulnerability: scoreLabel(comp.vulnerability ?? 0),
    accessibility: accessLabel(comp.response ?? 0),
    factors,
    recommendation: detail?.recommendation ?? (h.level === 'high' || h.level === 'critical' ? 'Relocation assessment' : 'Monitor'),
    exposedPopulation: h.exposed_population,
    exposedAreaPercent: h.exposed_area_percent ?? 0,
    meanHazard: h.mean_hazard ?? 0,
    maxHazard: h.max_hazard ?? 0,
    priorityRank: h.priority_rank,
    priorityScore: h.priority_score,
    confidence: h.confidence,
    hazardType: h.hazard_type,
    detail,
  }
}

function toSite(s: ApiSite): ConsoleSite {
  const cap = Object.fromEntries(s.constraints.map((c) => [c.name, c.capacity]))
  return {
    id: s.candidate_id,
    name: s.candidate_id.replace('cand-', 'Site '),
    coordinates: [s.lon, s.lat],
    status: s.screening_status === 'FEASIBLE' ? 'feasible' : 'review',
    safety: Math.round(s.safety_score),
    healthcare: Math.round(s.healthcare_access_score),
    accessibility: Math.round(s.road_access_score),
    infrastructure: Math.round(s.terrain_score),
    environment: Math.round(100 - s.mean_susceptibility),
    currentPopulation: s.current_population,
    capacity: {
      land: cap.land ?? 0,
      healthcare: cap.healthcare ?? 0,
      environment: cap.environmental ?? 0,
      infrastructure: cap.infrastructure ?? 0,
      accessibility: cap.accessibility ?? 0,
    },
    suitability: s.suitability_score,
    screeningStatus: s.screening_status,
    bindingConstraint: s.binding_constraint === 'environmental' ? 'environment' : s.binding_constraint,
    meanSusceptibility: s.mean_susceptibility,
    distanceKm: s.distance_from_habitation_km,
    constraints: s.constraints,
    areaKm2: s.area_km2,
    effectiveCapacity: s.effective_capacity,
    availableCapacity: s.available_capacity,
  }
}

/**
 * Fold a detail response into a summary row.
 *
 * The list endpoint carries no component scores, so vulnerability and response
 * initially fall back to 0 and label as "Low"/"Good". Without this the panel
 * showed "Vulnerability: Low" directly above evidence reading "23 deg slope",
 * which is a contradiction on one screen.
 */
export function enrichHabitation(h: ConsoleHabitation, detail: ApiHabitationDetail): ConsoleHabitation {
  return {
    ...h,
    hazardExposure: hazardLabel(detail.mean_hazard ?? h.meanHazard),
    vulnerability: scoreLabel(detail.components.vulnerability ?? 0),
    accessibility: accessLabel(detail.components.response ?? 0),
    factors: detail.explanation.contributions.map((c) => ({
      id: c.id, label: c.label, value: c.contribution, evidence: c.evidence,
    })),
    recommendation: detail.recommendation,
    detail,
  }
}

function fallbackRegion(): RegionSummary {
  return {
    hazardType: 'landslide', hazardModel: null,
    name: mockRegion.name, code: mockRegion.code, state: 'Himachal Pradesh',
    primaryHazard: 'Landslide susceptibility', areaKm2: 0,
    settlements: mockHabitations.length,
    districtPopulation: mockRegion.exposed, districtExposed: mockRegion.exposed,
    settlementPopulation: mockRegion.exposed, settlementExposed: mockRegion.exposed,
    critical: mockRegion.critical, high: mockRegion.highRisk,
    redZoneAreaKm2: 0, candidateSites: mockSites.length, feasibleSites: mockSites.length,
    updatedAt: mockRegion.updatedAt, modelVersion: 'development-fixture',
    disclaimer: 'Development fixture — the analytical API was unreachable. These numbers are not analysis.',
    provenance: [],
  }
}

const fallbackHabitations = (): ConsoleHabitation[] =>
  mockHabitations.map((h, i) => ({
    ...h,
    exposedPopulation: 0, exposedAreaPercent: 0, meanHazard: h.risk, maxHazard: h.risk,
    priorityRank: i + 1, priorityScore: h.risk, confidence: 'LOW' as Confidence,
    hazardType: 'landslide' as HazardType,
  }))

const fallbackSites = (): ConsoleSite[] =>
  mockSites.map((s) => ({
    ...s, suitability: s.safety, screeningStatus: 'REVIEW', bindingConstraint: 'infrastructure',
    meanSusceptibility: 0, distanceKm: null, constraints: [], areaKm2: 0,
    effectiveCapacity: Math.min(...Object.values(s.capacity)),
    availableCapacity: Math.max(0, Math.min(...Object.values(s.capacity)) - s.currentPopulation),
  }))

export type ConsoleSnapshot = {
  mode: DataMode
  region: RegionSummary
  habitations: ConsoleHabitation[]
  message?: string
}

export interface IntelligenceProvider {
  getSnapshot(): Promise<ConsoleSnapshot>
  getHabitationDetail(id: string): Promise<ApiHabitationDetail | null>
  getSites(habitationId?: string): Promise<ConsoleSite[]>
  getCapacity(siteId: string, habitationId?: string): Promise<ConsoleSite | null>
  runOptimization(habitationIds?: string[]): Promise<import('./api').ApiOptimization | null>
  runScenario(p: ScenarioParameters): Promise<import('./api').ApiScenario | null>
  getBrief(id: string): Promise<import('./api').ApiBrief | null>
}

export const intelligenceProvider: IntelligenceProvider = {
  async getSnapshot() {
    try {
      const [region, rows] = await Promise.all([api.region(), api.habitations(400)])
      return {
        mode: 'analytical',
        region: {
          hazardType: region.hazard_type, hazardModel: region.hazard_model,
          name: region.name, code: region.code, state: region.state,
          primaryHazard: region.primary_hazard, areaKm2: region.area_km2,
          settlements: region.settlements,
          districtPopulation: region.district_population,
          districtExposed: region.district_exposed_population,
          settlementPopulation: region.settlement_population,
          settlementExposed: region.settlement_exposed_population,
          critical: region.levels.critical ?? 0,
          high: region.levels.high ?? 0,
          redZoneAreaKm2: region.red_zone_area_km2,
          candidateSites: region.candidate_sites,
          feasibleSites: region.feasible_sites,
          updatedAt: region.updated_at, modelVersion: region.model_version,
          disclaimer: region.disclaimer, provenance: region.provenance,
        },
        habitations: rows.map((h) => toHabitation(h)),
      }
    } catch (err) {
      return {
        mode: 'fallback',
        region: fallbackRegion(),
        habitations: fallbackHabitations(),
        message: `Analytical API unreachable (${(err as Error).message}). Showing development fixture.`,
      }
    }
  },

  async getHabitationDetail(id) {
    try {
      return await api.habitation(id)
    } catch {
      return null
    }
  },

  async getSites(habitationId) {
    try {
      return (await api.sites(habitationId, 6)).map(toSite)
    } catch {
      return fallbackSites()
    }
  },

  async getCapacity(siteId, habitationId) {
    try {
      return toSite(await api.capacity(siteId, habitationId))
    } catch {
      return null
    }
  },

  async runOptimization(habitationIds) {
    try {
      return await api.optimize({ habitation_ids: habitationIds, max_distance_km: 40 })
    } catch {
      return null
    }
  },

  async runScenario(p) {
    try {
      return await api.scenario({
        rainfall_delta_percent: p.rainfall,
        population_delta_percent: p.population,
        road_availability_percent: p.roads,
      })
    } catch {
      return null
    }
  },

  async getBrief(id) {
    try {
      return await api.brief(id)
    } catch {
      return null
    }
  },
}

/** Retained for the relocation panel's "nearest site" convenience. */
export function getNearestSite(habitation: { coordinates: [number, number] }, candidates: ConsoleSite[]) {
  return candidates.reduce<ConsoleSite | undefined>((nearest, candidate) => {
    if (!nearest) return candidate
    return distance(point(habitation.coordinates), point(candidate.coordinates)) <
      distance(point(habitation.coordinates), point(nearest.coordinates))
      ? candidate
      : nearest
  }, undefined)
}

export { calculateOptimization, calculateScenario }
