/* =========================================================================
   DEVELOPMENT FIXTURE — NOT ANALYTICAL TRUTH
   =========================================================================

   Everything below (Village A-D, Site A-C, the risk values, the contribution
   figures, the region counts) was hand-authored before the analytical pipeline
   existed. None of it is derived from data.

   The authoritative path is:
       src/data/provider.ts -> FastAPI (apps/api) -> services/ -> data/processed

   This file survives for two reasons only:
     1. it defines the shared TypeScript shapes the panels render, and
     2. it is the offline fixture used when the API is unreachable — in which
        case the console shows a DEVELOPMENT FIXTURE banner so these numbers
        can never be mistaken for analysis.

   Do not add analytical values here. Do not read from it in a component.
   ========================================================================= */

export type RiskLevel = 'critical' | 'high' | 'monitor' | 'safe'
export type RiskFactor = { id: string; label: string; value: number; evidence: string }
export type CapacityProfile = { land: number; healthcare: number; environment: number; infrastructure: number; accessibility: number }
export type Habitation = { id: string; name: string; district: string; coordinates: [number, number]; risk: number; level: RiskLevel; population: number; hazardExposure: string; vulnerability: string; accessibility: string; factors: RiskFactor[]; recommendation: string }
export type RelocationSite = { id: string; name: string; coordinates: [number, number]; status: 'feasible' | 'review'; safety: number; healthcare: number; accessibility: number; infrastructure: number; environment: number; currentPopulation: number; capacity: CapacityProfile }
export type ScenarioParameters = { rainfall: number; roads: number; population: number }
export type ScenarioResult = { parameters: ScenarioParameters; critical: number; highRiskPopulation: number; relocationAssessments: number; riskMultiplier: number; accessibilityDelta: number }
export type Allocation = { sourceId: string; sourceName: string; destinationId: string; destinationName: string; population: number; feasible: boolean }
export type OptimizationResult = { allocations: Allocation[]; status: 'optimal' | 'feasible' | 'unavailable'; constraints: string[] }

export const region = { name: 'Kangra Pilot Region', code: 'HP-04', critical: 12, highRisk: 27, exposed: 18420, updatedAt: '08 SEP 2026 · 14:32 IST' }
const factorSet = (factors: Array<[string, number, string]>): RiskFactor[] => factors.map(([label, value, evidence], index) => ({ id: `${label}-${index}`, label, value, evidence }))

export const habitations: Habitation[] = [
  { id: 'village-a', name: 'Village A', district: 'Dharamshala Block', coordinates: [76.3234, 32.219], risk: 87, level: 'critical', population: 4830, hazardExposure: 'Very high', vulnerability: 'High', accessibility: 'Poor', factors: factorSet([['Historical hazard exposure', 25, 'Repeated high-intensity events in the local catchment'], ['Population exposure', 22, '4,830 residents within the modeled exposure area'], ['Poor accessibility', 18, 'Primary access route exceeds the response threshold'], ['Steep slope', 12, 'Terrain increases evacuation friction'], ['Healthcare access', 10, 'Nearest facility is outside the preferred response time']]), recommendation: 'Relocation assessment' },
  { id: 'village-b', name: 'Village B', district: 'Nagrota Block', coordinates: [76.268, 32.137], risk: 73, level: 'high', population: 2140, hazardExposure: 'High', vulnerability: 'High', accessibility: 'Moderate', factors: factorSet([['Historical hazard exposure', 22, 'High recurrence across the upstream drainage'], ['Population exposure', 18, 'Dense settlement pattern increases exposure'], ['Road fragility', 14, 'Two access segments are vulnerable during heavy rain'], ['Slope instability', 11, 'Moderate slope exposure compounds hazard'], ['Healthcare access', 8, 'Limited nearby surge capacity']]), recommendation: 'Priority mitigation' },
  { id: 'village-c', name: 'Village C', district: 'Baijnath Block', coordinates: [76.647, 32.05], risk: 61, level: 'high', population: 1220, hazardExposure: 'High', vulnerability: 'Moderate', accessibility: 'Good', factors: factorSet([['Historical hazard exposure', 18, 'Seasonal hazard signal remains elevated'], ['Population exposure', 14, 'Residential footprint overlaps the risk zone'], ['Road fragility', 11, 'Secondary route has limited redundancy'], ['Slope instability', 10, 'Terrain is sensitive near the settlement edge'], ['Healthcare access', 8, 'Capacity is adequate but distant']]), recommendation: 'Monitor and prepare' },
  { id: 'village-d', name: 'Village D', district: 'Palampur Block', coordinates: [76.535, 32.112], risk: 44, level: 'monitor', population: 980, hazardExposure: 'Moderate', vulnerability: 'Moderate', accessibility: 'Good', factors: factorSet([['Historical hazard exposure', 13, 'Moderate historical signal'], ['Population exposure', 10, 'Low-density exposure footprint'], ['Road fragility', 8, 'Route remains usable under modeled conditions'], ['Slope instability', 7, 'Localized slope sensitivity'], ['Healthcare access', 6, 'Adequate access to nearby facilities']]), recommendation: 'Monitor' },
]

export const sites: RelocationSite[] = [
  { id: 'site-a', name: 'Site A', coordinates: [76.407, 32.245], status: 'feasible', safety: 94, healthcare: 88, accessibility: 91, infrastructure: 86, environment: 87, currentPopulation: 1800, capacity: { land: 7800, healthcare: 7600, environment: 7500, infrastructure: 7200, accessibility: 8100 } },
  { id: 'site-b', name: 'Site B', coordinates: [76.215, 32.265], status: 'feasible', safety: 89, healthcare: 82, accessibility: 86, infrastructure: 78, environment: 84, currentPopulation: 1100, capacity: { land: 4500, healthcare: 4200, environment: 4000, infrastructure: 3800, accessibility: 4700 } },
  { id: 'site-c', name: 'Site C', coordinates: [76.56, 32.2], status: 'review', safety: 81, healthcare: 75, accessibility: 84, infrastructure: 73, environment: 78, currentPopulation: 640, capacity: { land: 2500, healthcare: 2300, environment: 2200, infrastructure: 2000, accessibility: 2600 } },
]

export const getEffectiveCapacity = (site: RelocationSite) => Math.min(...Object.values(site.capacity))
export const getAvailableCapacity = (site: RelocationSite) => Math.max(0, getEffectiveCapacity(site) - site.currentPopulation)
export const canAccommodate = (site: RelocationSite, habitation: Habitation) => getAvailableCapacity(site) >= habitation.population
export const getBindingConstraint = (site: RelocationSite) => Object.entries(site.capacity).sort(([, left], [, right]) => left - right)[0][0] as keyof CapacityProfile

export function calculateScenario(parameters: ScenarioParameters): ScenarioResult {
  const rainfallImpact = parameters.rainfall * 0.14
  const accessImpact = Math.max(0, 100 - parameters.roads) * 0.08
  const populationImpact = parameters.population * 0.06
  return { parameters, critical: Math.round(region.critical + rainfallImpact + accessImpact + populationImpact), highRiskPopulation: Math.round(region.exposed + parameters.rainfall * 72 + (100 - parameters.roads) * 48 + parameters.population * 82), relocationAssessments: Math.round(8 + parameters.rainfall * 0.08 + (100 - parameters.roads) * 0.06 + parameters.population * 0.07), riskMultiplier: 1 + (rainfallImpact + accessImpact + populationImpact) / 100, accessibilityDelta: Math.round(100 - parameters.roads) }
}

export function calculateOptimization(): OptimizationResult {
  const available = sites.map((site) => ({ site, remaining: getAvailableCapacity(site) }))
  const allocations: Allocation[] = []
  habitations.slice(0, 3).forEach((habitation) => {
    let remaining = habitation.population
    available.forEach((destination) => {
      if (remaining <= 0) return
      const population = Math.min(remaining, destination.remaining)
      if (population > 0) { allocations.push({ sourceId: habitation.id, sourceName: habitation.name, destinationId: destination.site.id, destinationName: destination.site.name, population, feasible: population === remaining }); destination.remaining -= population; remaining -= population }
    })
  })
  return { allocations, status: allocations.length > 0 && allocations.every((allocation) => allocation.feasible) ? 'optimal' : 'feasible', constraints: ['Safety', 'Capacity', 'Accessibility', 'Environment'] }
}
