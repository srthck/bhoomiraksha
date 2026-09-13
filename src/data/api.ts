/**
 * Typed client for the Bhoomi Raksha analytical API.
 *
 * The browser never computes an analytical value. Every number rendered by the
 * console arrives through one of these calls, which are served by FastAPI from
 * the processed Kangra pilot artefacts.
 */

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

export type RiskLevel = 'critical' | 'high' | 'monitor' | 'safe'
export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW'
export type ScreeningStatus = 'FEASIBLE' | 'REVIEW' | 'REJECTED'
/** The architecture names several hazards; only 'landslide' has a pipeline in the Kangra pilot. */
export type HazardType = 'landslide' | 'earthquake' | 'flood' | 'cyclone'

export type ApiHazardModel = {
  type: HazardType
  label: string
  index_label: string
  susceptibility_label: string
  model_name: string
  method: string
  assessment: string
  /** Share of the susceptibility index per factor — not model accuracy, not probability. */
  basis: { factor: string; label: string; weight: number }[]
  hazard_mean_weight: number
  hazard_peak_weight: number
  risk_weights: Record<string, number>
  risk_labels: Record<string, string>
  validated: boolean
  meaning: string
}

export type ApiProvenance = {
  source: string
  source_resolution: string | null
  processing: string | null
  validation_status: string
  proxy: boolean
  limitations: string[]
}

export type ApiRegion = {
  hazard_type: HazardType
  hazard_model: ApiHazardModel
  name: string
  code: string
  state: string
  area_km2: number
  primary_hazard: string
  settlements: number
  district_population: number
  district_exposed_population: number
  settlement_population: number
  settlement_exposed_population: number
  levels: Record<string, number>
  red_zone_area_km2: number
  candidate_sites: number
  feasible_sites: number
  updated_at: string
  model_version: string
  provenance: ApiProvenance[]
  disclaimer: string
}

export type ApiHabitation = {
  id: string
  name: string
  place: string | null
  lon: number
  lat: number
  population: number
  exposed_population: number
  exposed_area_percent: number | null
  mean_hazard: number | null
  max_hazard: number | null
  risk_score: number
  level: RiskLevel
  priority_rank: number
  priority_score: number
  confidence: Confidence
  hazard_type: HazardType
}

export type ApiContribution = {
  id: string
  label: string
  component_score: number
  weight: number
  contribution: number
  evidence: string
}

export type ApiHabitationDetail = ApiHabitation & {
  hazard_model: ApiHazardModel
  hazard: {
    type: HazardType
    mean_susceptibility: number | null
    peak_susceptibility: number | null
    hazard_component: number
  }
  risk_display: number
  site_slope_mean_deg: number | null
  dist_to_road_m: number | null
  dist_to_major_road_m: number | null
  dist_to_health_m: number | null
  footprint_source: string
  analysed_area_km2: number | null
  components: Record<string, number>
  contributions: Record<string, number>
  explanation: { method: string; note: string; contributions: ApiContribution[]; total: number }
  data_quality: {
    confidence: Confidence
    reasons: string[]
    footprint_source: string | null
    population_source: string
    hazard_validation: string
    accessibility_method: string
  }
  recommendation: string
}

export type ApiCapacityConstraint = {
  name: string
  capacity: number
  derivation: string
  is_binding: boolean
}

export type ApiSite = {
  candidate_id: string
  lon: number
  lat: number
  area_km2: number
  mean_susceptibility: number
  max_susceptibility: number
  mean_slope_deg: number
  distance_to_road_m: number
  distance_to_major_road_m: number
  distance_to_healthcare_m: number
  current_population: number
  suitability_score: number
  screening_status: ScreeningStatus
  safety_score: number
  terrain_score: number
  road_access_score: number
  healthcare_access_score: number
  effective_capacity: number
  available_capacity: number
  binding_constraint: string
  constraints: ApiCapacityConstraint[]
  distance_from_habitation_km: number | null
}

export type ApiAllocation = {
  source_id: string
  source_name: string
  site_id: string
  population: number
  distance_km: number
  site_suitability: number
}

export type ApiOptimization = {
  solver_status: string
  objective_value: number
  allocations: ApiAllocation[]
  total_relocated: number
  unallocated_population: number
  unmet_by_source: { source_id: string; source_name: string; unallocated: number }[]
  site_utilization: { site_id: string; allocated: number; available_capacity: number; utilisation_percent: number }[]
  constraint_summary: string[]
  sources: number
  sinks: number
  config: Record<string, unknown>
  objective_description: string
}

export type ApiScenarioDelta = { label: string; baseline: number; scenario: number; delta: number; unit: string }

export type ApiScenario = {
  parameters: { rainfall_delta_percent: number; population_delta_percent: number; road_availability_percent: number }
  deltas: ApiScenarioDelta[]
  baseline_levels: Record<string, number>
  scenario_levels: Record<string, number>
  changed_habitations: { id: string; name: string; from: RiskLevel; to: RiskLevel; risk_baseline: number; risk_scenario: number }[]
  top_priority_baseline: string
  top_priority_scenario: string
  optimization: ApiOptimization
  propagation_notes: string[]
  runtime_ms: number
}

export type ApiBrief = {
  region: string
  primary_hazard: string
  hazard_type: HazardType
  index_label: string
  habitation: ApiHabitation
  observed: Record<string, unknown>
  derived: Record<string, unknown>
  recommended: Record<string, unknown>
  preferred_site: ApiSite | null
  optimization: ApiOptimization | null
  data_confidence: Confidence
  confidence_reasons: string[]
  limitations: string[]
  disclaimer: string
  generated_at: string
  model_version: string
}

export type RedZones = {
  type: 'FeatureCollection'
  features: GeoJSON.Feature[]
  meta: { count: number; total_area_km2: number; threshold: string; note: string }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<{ status: string }>('/api/health'),
  region: () => get<ApiRegion>('/api/region'),
  habitations: (limit = 400) => get<ApiHabitation[]>(`/api/habitations?limit=${limit}`),
  priority: (limit = 25) => get<ApiHabitation[]>(`/api/priority?limit=${limit}`),
  habitation: (id: string) => get<ApiHabitationDetail>(`/api/habitations/${id}`),
  exposure: (id: string) => get<Record<string, unknown>>(`/api/exposure/${id}`),
  redZones: (minAreaKm2 = 0.15) => get<RedZones>(`/api/hazard/red-zones?min_area_km2=${minAreaKm2}`),
  susceptibility: () => get<Record<string, unknown>>('/api/hazard/susceptibility'),
  sites: (habitationId?: string, limit = 6) =>
    get<ApiSite[]>(`/api/relocation/sites?limit=${limit}${habitationId ? `&habitation_id=${habitationId}` : ''}`),
  capacity: (siteId: string, habitationId?: string) =>
    get<ApiSite>(`/api/capacity/${siteId}${habitationId ? `?habitation_id=${habitationId}` : ''}`),
  optimize: (body: { habitation_ids?: string[]; max_distance_km?: number; allow_review_sites?: boolean }) =>
    post<ApiOptimization>('/api/optimization/run', body),
  scenario: (body: { rainfall_delta_percent: number; population_delta_percent: number; road_availability_percent: number }) =>
    post<ApiScenario>('/api/scenario/run', body),
  brief: (id: string) => get<ApiBrief>(`/api/executive-brief/${id}`),
}
