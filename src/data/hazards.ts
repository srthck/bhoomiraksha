import type { HazardType } from './api'

/**
 * Display names per hazard type. This is a naming table only: it does not make
 * a hazard available. Availability comes from the API's hazard model, and in
 * the Kangra pilot the only model with a real pipeline is landslide.
 */
const HAZARD_NAMES: Record<HazardType, string> = {
  landslide: 'Landslide',
  earthquake: 'Earthquake',
  flood: 'Flood',
  cyclone: 'Cyclone',
}

export const hazardName = (type: HazardType) => HAZARD_NAMES[type]

/** "Landslide risk index" — never a bare "risk index". */
export const riskIndexLabel = (type: HazardType) => `${HAZARD_NAMES[type]} risk index`

export const susceptibilityLabel = (type: HazardType) => `${HAZARD_NAMES[type]} susceptibility`

/** Half-up, identical to the API's display rounding. */
export const displayRisk = (score: number) => Math.round(score)
