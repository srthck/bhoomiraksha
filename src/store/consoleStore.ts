import { create } from 'zustand'
import type { ApiBrief, ApiOptimization, ApiScenario } from '../data/api'
import {
  enrichHabitation,
  intelligenceProvider,
  type ConsoleHabitation,
  type ConsoleSite,
  type DataMode,
  type RegionSummary,
} from '../data/provider'
import type { ScenarioParameters } from '../data/mock'

export type ConsoleMode =
  | 'regional' | 'investigate' | 'explain' | 'relocation'
  | 'capacity' | 'optimization' | 'scenario' | 'executive'

export type LayerKey =
  | 'susceptibility' | 'historical' | 'rainfall' | 'habitations' | 'population'
  | 'infrastructure' | 'roads' | 'hospitals' | 'candidateSites' | 'capacity'
  | 'redZones'

export type ConsoleState = {
  /* dataset, loaded from the analytical API */
  loaded: boolean
  mode_data: DataMode
  dataMessage?: string
  region: RegionSummary | null
  habitations: ConsoleHabitation[]

  /* selection + workflow */
  mode: ConsoleMode
  selectedHabitation: ConsoleHabitation | null
  selectedSite: ConsoleSite | null
  sites: ConsoleSite[]
  sitesLoading: boolean
  activeLayers: Record<LayerKey, boolean>

  scenarioParameters: ScenarioParameters
  scenarioResult: ApiScenario | null
  scenarioRunning: boolean
  optimizationResult: ApiOptimization | null
  optimizationRunning: boolean
  brief: ApiBrief | null

  load: () => Promise<void>
  selectHabitation: (h: ConsoleHabitation) => Promise<void>
  selectSite: (s: ConsoleSite) => Promise<void>
  setMode: (m: ConsoleMode) => void
  toggleLayer: (l: LayerKey) => void
  setScenarioParameter: (k: keyof ScenarioParameters, v: number) => void
  runScenario: () => Promise<void>
  runOptimization: () => Promise<void>
  openBrief: () => Promise<void>
  reset: () => void
}

const initialLayers: Record<LayerKey, boolean> = {
  susceptibility: true, historical: false, rainfall: false, habitations: true,
  population: false, infrastructure: false, roads: false, hospitals: false,
  candidateSites: false, capacity: false, redZones: true,
}
const initialScenario: ScenarioParameters = { rainfall: 25, roads: 85, population: 10 }

const RELOCATION_MODES: ConsoleMode[] = ['relocation', 'capacity', 'optimization']

export const useConsoleStore = create<ConsoleState>((set, get) => ({
  loaded: false,
  mode_data: 'analytical',
  region: null,
  habitations: [],

  mode: 'regional',
  selectedHabitation: null,
  selectedSite: null,
  sites: [],
  sitesLoading: false,
  activeLayers: initialLayers,

  scenarioParameters: initialScenario,
  scenarioResult: null,
  scenarioRunning: false,
  optimizationResult: null,
  optimizationRunning: false,
  brief: null,

  load: async () => {
    const snap = await intelligenceProvider.getSnapshot()
    set({
      loaded: true, mode_data: snap.mode, dataMessage: snap.message,
      region: snap.region, habitations: snap.habitations,
    })
  },

  // Selecting fetches the full explanation for that settlement; the summary
  // list deliberately does not carry 1,183 explanations.
  selectHabitation: async (h) => {
    set({ selectedHabitation: h, selectedSite: null, mode: 'investigate' })
    const detail = await intelligenceProvider.getHabitationDetail(h.id)
    if (!detail) return
    const enriched = enrichHabitation(h, detail)
    set((s) => (s.selectedHabitation?.id === h.id ? { selectedHabitation: enriched } : {}))
  },

  selectSite: async (s) => {
    set({ selectedSite: s, mode: 'capacity' })
    const hab = get().selectedHabitation
    const full = await intelligenceProvider.getCapacity(s.id, hab?.id)
    if (full) set((st) => (st.selectedSite?.id === s.id ? { selectedSite: full } : {}))
  },

  setMode: (mode) => {
    set((state) => ({
      mode,
      activeLayers: RELOCATION_MODES.includes(mode)
        ? { ...state.activeLayers, candidateSites: true }
        : state.activeLayers,
    }))
    // Candidate discovery is a query against the site screen, not a static list.
    if (mode === 'relocation') {
      const { selectedHabitation } = get()
      set({ sitesLoading: true })
      void intelligenceProvider.getSites(selectedHabitation?.id).then((sites) =>
        set({ sites, sitesLoading: false }))
    }
  },

  toggleLayer: (layer) =>
    set((s) => ({ activeLayers: { ...s.activeLayers, [layer]: !s.activeLayers[layer] } })),

  setScenarioParameter: (key, value) =>
    set((s) => ({ scenarioParameters: { ...s.scenarioParameters, [key]: value }, scenarioResult: null })),

  runScenario: async () => {
    set({ scenarioRunning: true, mode: 'scenario' })
    const result = await intelligenceProvider.runScenario(get().scenarioParameters)
    set({ scenarioResult: result, scenarioRunning: false })
  },

  runOptimization: async () => {
    set({ optimizationRunning: true, mode: 'optimization' })
    const hab = get().selectedHabitation
    const result = await intelligenceProvider.runOptimization(hab ? [hab.id] : undefined)
    set({ optimizationResult: result, optimizationRunning: false })
  },

  openBrief: async () => {
    const { selectedHabitation, habitations } = get()
    const target = selectedHabitation ?? habitations[0]
    set({ mode: 'executive' })
    if (!target) return
    const brief = await intelligenceProvider.getBrief(target.id)
    set({ brief })
  },

  reset: () => set({
    mode: 'regional', selectedHabitation: null, selectedSite: null, sites: [],
    activeLayers: initialLayers, scenarioParameters: initialScenario,
    scenarioResult: null, optimizationResult: null, brief: null,
  }),
}))
