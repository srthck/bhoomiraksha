import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Map, { Marker, NavigationControl, useControl, type MapRef } from 'react-map-gl/maplibre'
import type { StyleSpecification } from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { ArcLayer, ScatterplotLayer } from '@deck.gl/layers'
import {
  Activity,
  ArrowRight,
  ChevronDown,
  FileText,
  Layers3,
  MapPin,
  Radio,
  Settings2,
  SlidersHorizontal,
} from 'lucide-react'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { ApiAllocation } from '../data/api'
import type { ConsoleHabitation, ConsoleSite } from '../data/provider'
import { useConsoleStore, type ConsoleMode, type LayerKey } from '../store/consoleStore'
import { AnimatedNumber, TIMING, compact, useReducedMotion } from '../motion/primitives'
import { HazardSignal } from '../motion/HazardSignal'
import { GLOBE_START, PILOT_CAMERA, buildMapStyle, prefetchRemoteStyle } from './basemap'
import { useEntrySequence } from './useEntrySequence'
import { hazardName } from '../data/hazards'
import {
  CapacityPanel,
  ExecutiveBrief,
  ExplainPanel,
  HabitationPanel,
  OptimizationPanel,
  RelocationPanel,
  ScenarioPanel,
} from './panels'
import '../styles/console.css'

const CHAIN = [
  'Hazard', 'Exposure', 'Vulnerability', 'Risk', 'Priority', 'Action',
  'Relocation', 'Capacity', 'Optimization', 'Scenario', 'Decision',
] as const
const CHAIN_MODES: ConsoleMode[] = [
  'investigate', 'investigate', 'explain', 'explain', 'relocation', 'relocation',
  'relocation', 'capacity', 'optimization', 'scenario', 'executive',
]

const LAYER_GROUPS: { label: string; items: [LayerKey, string, boolean][] }[] = [
  { label: 'Hazard', items: [['susceptibility', 'Susceptibility', true], ['historical', 'Historical events', false], ['rainfall', 'Rainfall', false]] },
  { label: 'Exposure', items: [['habitations', 'Habitations', true], ['population', 'Population', false], ['infrastructure', 'Infrastructure', false]] },
  { label: 'Response', items: [['roads', 'Roads', false], ['hospitals', 'Hospitals', false]] },
  { label: 'Relocation', items: [['candidateSites', 'Candidate sites', true], ['capacity', 'Capacity', false]] },
]

/** Stable identities so the deck layer memo is not invalidated every render. */
const EMPTY_ALLOCATIONS: ApiAllocation[] = []
const EMPTY_HABITATIONS: ConsoleHabitation[] = []

/* ------------------------------------------------------------ deck layers -- */

function DeckOverlay({
  habitations,
  sites,
  selectedHabitation,
  showSites,
  allocations,
  levelOf,
  hazardOpacity,
}: {
  habitations: ConsoleHabitation[]
  sites: ConsoleSite[]
  selectedHabitation: ConsoleHabitation | null
  showSites: boolean
  allocations: ApiAllocation[]
  levelOf: (h: ConsoleHabitation) => string
  hazardOpacity: number
}) {
  const layers = useMemo(() => {
    // Shader linking is the single most expensive thing deck does, and it
    // happens the first time a layer actually draws. So the scatterplot
    // program is warmed at mount — this layer draws from the first frame,
    // while the landing still covers the screen and the camera has not moved.
    // At globe zoom a 2.2km radius is well under a pixel, so nothing is
    // visible until the descent brings it into scale, exactly as before.
    // site-halo and selected-habitation reuse this same program and are
    // therefore free; ArcLayer is a second program, so it is added only once
    // routes exist — that happens on a click, long after the cinematic.
    const hazard = new ScatterplotLayer({
      id: 'hazard-field',
      data: habitations,
      getPosition: (d: ConsoleHabitation) => d.coordinates,
      getRadius: (d: ConsoleHabitation) => (d.risk > 80 ? 2200 : 1400),
      getFillColor: (d: ConsoleHabitation) =>
        levelOf(d) === 'critical'
          ? [232, 80, 63, Math.round(52 * hazardOpacity)]
          : [232, 145, 63, Math.round(38 * hazardOpacity)],
      getLineColor: (d: ConsoleHabitation) =>
        levelOf(d) === 'critical'
          ? [240, 104, 88, Math.round(190 * hazardOpacity)]
          : [238, 158, 84, Math.round(155 * hazardOpacity)],
      stroked: true,
      lineWidthMinPixels: 1,
      transitions: { getFillColor: 600, getLineColor: 600 },
      updateTriggers: { getFillColor: [hazardOpacity, levelOf], getLineColor: [hazardOpacity, levelOf] },
    })

    const siteHalo = new ScatterplotLayer({
      id: 'site-halo',
      visible: showSites,
      data: sites,
      getPosition: (d: ConsoleSite) => d.coordinates,
      getRadius: 900,
      getFillColor: [111, 208, 140, 44],
      getLineColor: [140, 226, 166, 170],
      stroked: true,
      lineWidthMinPixels: 2,
    })

    const routes = allocations
      .map((a) => ({
        a,
        source: habitations.find((h) => h.id === a.source_id),
        target: sites.find((s) => s.id === a.site_id),
      }))
      .filter((r): r is { a: ApiAllocation; source: ConsoleHabitation; target: ConsoleSite } =>
        Boolean(r.source && r.target))

    const arcs = routes.length
      ? new ArcLayer({
          id: 'allocation-routes',
          data: routes,
          getSourcePosition: (r: { source: ConsoleHabitation }) => r.source.coordinates,
          getTargetPosition: (r: { target: ConsoleSite }) => r.target.coordinates,
          getSourceColor: [240, 163, 75, 220],
          getTargetColor: [111, 208, 140, 230],
          getWidth: 4,
          getHeight: 0.35,
        })
      : null

    const selected = new ScatterplotLayer({
          id: 'selected-habitation',
          data: selectedHabitation ? [selectedHabitation] : EMPTY_HABITATIONS,
          getPosition: (d: ConsoleHabitation) => d.coordinates,
          getRadius: 320,
          getFillColor: [255, 246, 228, 210],
          getLineColor: [255, 120, 100, 255],
          lineWidthMinPixels: 3,
          stroked: true,
        })

    return [hazard, siteHalo, ...(arcs ? [arcs] : []), selected]
  }, [habitations, sites, selectedHabitation, showSites, allocations, levelOf, hazardOpacity])

  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay({ layers }))
  // only push when the memoised array actually changes — calling setProps on
  // every parent render made deck diff every layer during camera animation
  useEffect(() => {
    overlay.setProps({ layers })
  }, [overlay, layers])
  return null
}

/* ----------------------------------------------------------------- chrome -- */

function DecisionChain({ mode }: { mode: ConsoleMode }) {
  const active = CHAIN_MODES.indexOf(mode)
  return (
    <div className="chain">
      <span className="eyebrow">Decision chain</span>
      <div className="chain-track">
        {CHAIN.map((label, i) => (
          <div className={`chain-item ${i < active ? 'done' : ''} ${i === active ? 'now' : ''}`} key={label}>
            <span className="chain-dot" />
            <span>{label}</span>
            {i < CHAIN.length - 1 && <i />}
          </div>
        ))}
      </div>
    </div>
  )
}

function LayerPanel() {
  const { activeLayers, toggleLayer } = useConsoleStore()
  return (
    <aside className="layer-panel glass">
      <div className="panel-head">
        <Layers3 size={14} />
        <span>Intelligence</span>
        <span className="panel-code">L-01</span>
      </div>
      {LAYER_GROUPS.map((g) => (
        <div className="layer-group" key={g.label}>
          <div>{g.label}</div>
          {g.items.map(([key, label, available]) => (
            <button
              key={key}
              className="layer-toggle"
              onClick={() => available && toggleLayer(key)}
              aria-pressed={available ? activeLayers[key] : false}
              disabled={!available}
            >
              <span className={`checkbox ${available && activeLayers[key] ? 'on' : ''}`} aria-hidden="true">
                {available && activeLayers[key] && (
                  <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M1.5 5.2 4 7.6 8.5 2.6" />
                  </svg>
                )}
              </span>
              <span>{label}</span>
              {!available && <small>offline</small>}
            </button>
          ))}
        </div>
      ))}
    </aside>
  )
}

/* ------------------------------------------------------------------ shell -- */

export default function CommandCenter({ arriving = false }: { arriving?: boolean }) {
  const reduced = useReducedMotion()
  const mapRef = useRef<MapRef>(null)
  const [style, setStyle] = useState<StyleSpecification | null>(null)
  const [allocRevealed, setAllocRevealed] = useState(0)
  const [scenarioRunning, setScenarioRunning] = useState(false)
  const [sweepKey, setSweepKey] = useState(0)

  const stage = useEntrySequence({ mapRef, active: arriving, reduced })
  // habitations light up as the camera arrives; chrome follows a beat later
  const markersLive = !arriving || stage === 'descend' || stage === 'settled'
  const chromeLive = !arriving || stage === 'settled'

  const {
    mode, selectedHabitation, selectedSite, activeLayers, scenarioResult, optimizationResult,
    selectHabitation, setMode, load, loaded, region, habitations, sites, mode_data, dataMessage,
    openBrief,
  } = useConsoleStore()

  useEffect(() => {
    void load()
  }, [load])

  const showSites = mode === 'relocation' || mode === 'capacity' || mode === 'optimization'
  // A scenario reclassifies real settlements; those markers are recoloured from
  // the solver's own output rather than scaled by an invented multiplier.
  const scenarioOverride = useMemo(() => {
    const m: Record<string, { to: string; risk_scenario: number }> = {}
    scenarioResult?.changed_habitations.forEach((c) => {
      m[c.id] = { to: c.to, risk_scenario: c.risk_scenario }
    })
    return m
  }, [scenarioResult])
  // entering relocation is the shift from threat to solution: hazard drops back
  const hazardOpacity = showSites ? 0.3 : 1

  // Scenario results replace the baseline counts while a scenario is active,
  // so the status strip never shows one world and the scenario panel another.
  const scenarioLevels = scenarioResult?.scenario_levels
  const critical = scenarioLevels ? (scenarioLevels.critical ?? 0) : (region?.critical ?? 0)
  const highRisk = scenarioLevels ? (scenarioLevels.high ?? 0) : (region?.high ?? 0)
  const exposedDelta = scenarioResult?.deltas.find((d) => d.label === 'Exposed population')
  const exposed = exposedDelta ? exposedDelta.scenario : (region?.settlementExposed ?? 0)

  useEffect(() => {
    let live = true
    void prefetchRemoteStyle().then((remote) => {
      if (live) setStyle(buildMapStyle(remote))
    })
    return () => {
      live = false
    }
  }, [])

  // routes appear one at a time so the allocation reads as a sequence of decisions
  useEffect(() => {
    if (mode !== 'optimization' || !optimizationResult) {
      setAllocRevealed(0)
      return
    }
    if (reduced) {
      setAllocRevealed(optimizationResult.allocations.length)
      return
    }
    setAllocRevealed(0)
    const timers = optimizationResult.allocations.map((_, i) =>
      window.setTimeout(() => setAllocRevealed(i + 1), 300 + i * 340),
    )
    return () => timers.forEach(window.clearTimeout)
  }, [mode, optimizationResult, reduced])

  // camera pulls back when the narrative turns to relocation candidates
  useEffect(() => {
    if (mode !== 'relocation' || !chromeLive) return
    mapRef.current?.flyTo({ center: [76.39, 32.19], zoom: 10.1, pitch: 22, duration: reduced ? 0 : 1100 })
  }, [mode, reduced, chromeLive])

  useEffect(() => setSweepKey((k) => k + 1), [mode, scenarioResult])

  const focus = (h: ConsoleHabitation) => {
    void selectHabitation(h)
    mapRef.current?.flyTo({
      center: h.coordinates,
      zoom: 12.4,
      pitch: 50,
      duration: reduced ? 0 : TIMING.camera * 1000,
    })
  }

  // One handler owns the whole simulate action. Splitting it across a capture
  // handler and the button's own onClick meant the state update disabled the
  // button mid-dispatch and the store action never ran.
  const runScenarioWithSweep = () => {
    setScenarioRunning(true)
    useConsoleStore.getState().runScenario()
    window.setTimeout(() => setScenarioRunning(false), reduced ? 0 : 900)
  }

  const visibleAllocations = useMemo(
    () => (mode === 'optimization' && optimizationResult
      ? optimizationResult.allocations.slice(0, allocRevealed)
      : EMPTY_ALLOCATIONS),
    [mode, optimizationResult, allocRevealed],
  )

  // Every settlement contributes its hazard field through deck, but only the
  // actionable set gets a DOM marker. Pinning 400 markers over a 130 km
  // district made them overlap into an unclickable mat and is not what the
  // approved design showed.
  const markerHabitations = useMemo(() => {
    const actionable = habitations.filter((h) => {
      const lvl = scenarioOverride[h.id]?.to ?? h.level
      return lvl === 'critical' || lvl === 'high'
    })
    return (actionable.length ? actionable : habitations).slice(0, 60)
  }, [habitations, scenarioOverride])

  const levelOf = useMemo(
    () => (h: ConsoleHabitation) => scenarioOverride[h.id]?.to ?? h.level,
    [scenarioOverride],
  )
  const focused = Boolean(selectedHabitation) && mode !== 'regional'

  const panel = (() => {
    if (!chromeLive) return null
    if (mode === 'investigate' && selectedHabitation) return <HabitationPanel habitation={selectedHabitation} />
    if (mode === 'explain' && selectedHabitation) return <ExplainPanel habitation={selectedHabitation} />
    if (mode === 'relocation') return <RelocationPanel habitation={selectedHabitation} selectedSite={selectedSite} />
    if (mode === 'capacity' && selectedSite) return <CapacityPanel site={selectedSite} habitation={selectedHabitation} />
    if (mode === 'optimization') return <OptimizationPanel habitation={selectedHabitation} revealed={allocRevealed} />
    if (mode === 'executive') return <ExecutiveBrief habitation={selectedHabitation} site={selectedSite} />
    return null
  })()

  const start = arriving && !reduced ? GLOBE_START : PILOT_CAMERA

  return (
    <main className={`console ${focused ? 'is-focused' : ''} ${arriving ? 'is-arriving' : ''} stage-${stage}`}>
      <div className="map-stage">
        {style && (
          <Map
            ref={mapRef}
            initialViewState={start}
            mapStyle={style}
            reuseMaps
            attributionControl={false}
            interactive={chromeLive}
            dragRotate
          >
            <DeckOverlay
              habitations={habitations}
              sites={sites}
              selectedHabitation={selectedHabitation}
              showSites={showSites && activeLayers.candidateSites}
              allocations={visibleAllocations}
              levelOf={levelOf}
              hazardOpacity={hazardOpacity}
            />
            {chromeLive && <NavigationControl position="bottom-right" showCompass={false} />}

            {markersLive &&
              activeLayers.habitations &&
              markerHabitations.map((h, i) => (
                <Marker
                  key={h.id}
                  longitude={h.coordinates[0]}
                  latitude={h.coordinates[1]}
                  anchor="center"
                  onClick={(e) => {
                    e.originalEvent.stopPropagation()
                    focus(h)
                  }}
                >
                  <button
                    className={`map-marker ${selectedHabitation?.id === h.id ? 'is-selected' : ''}`}
                    // critical locations activate first — they are the payoff of the approach
                    style={{ '--arrive-delay': `${(h.level === 'critical' ? 0 : 220) + i * 130}ms` } as React.CSSProperties}
                    aria-label={`${h.name}, ${h.level} ${hazardName(h.hazardType).toLowerCase()} risk index ${h.risk}. Investigate.`}
                  >
                    <HazardSignal level={levelOf(h) as 'critical' | 'high' | 'monitor' | 'safe'} size="sm" />
                    <b>{Math.round(scenarioOverride[h.id]?.risk_scenario ?? h.risk)}</b>
                  </button>
                </Marker>
              ))}

            {chromeLive &&
              showSites &&
              activeLayers.candidateSites &&
              sites.map((s) => (
                <Marker key={s.id} longitude={s.coordinates[0]} latitude={s.coordinates[1]} anchor="center">
                  <button
                    className={`site-marker ${selectedSite?.id === s.id ? 'is-selected' : ''}`}
                    onClick={() => void useConsoleStore.getState().selectSite(s)}
                    aria-label={`Select ${s.name}`}
                  >
                    <MapPin size={14} />
                  </button>
                </Marker>
              ))}
          </Map>
        )}

        <div className="map-vignette" aria-hidden="true" />

        {!reduced && chromeLive && (
          <motion.div
            key={sweepKey}
            className="map-sweep"
            aria-hidden="true"
            initial={{ opacity: 0, x: '-10%' }}
            animate={{ opacity: [0, 0.5, 0], x: '110%' }}
            transition={{ duration: 0.95, ease: 'easeInOut' }}
          />
        )}

        <AnimatePresence>
          {arriving && !chromeLive && (
            <motion.div
              className="approach-hud"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <span className="eyebrow">Bhoomi Raksha</span>
              <strong>
                {stage === 'rotate' && 'LOCATING INDIA'}
                {stage === 'india' && 'INDIA · NATIONAL VIEW'}
                {stage === 'descend' && `${(region?.name ?? 'KANGRA DISTRICT').toUpperCase()} · ${region?.code ?? 'HP-KAN'}`}
                {stage === 'idle' && 'INITIALISING'}
              </strong>
              <small>
                {stage === 'descend'
                  ? 'Loading hazard field · identifying vulnerable habitations'
                  : 'Entering the geospatial decision system'}
              </small>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {chromeLive && (
        <>
          <header className="console-top">
            <button className="console-brand" onClick={() => setMode('regional')}>
              <span>
                <strong>
                  BHOOMI <em>RAKSHA</em>
                </strong>
                <small>Geospatial decision intelligence</small>
              </span>
            </button>
            <div className="top-actions">
              <button
                className={`ghost-action ${mode === 'scenario' ? 'is-active' : ''}`}
                onClick={() => setMode('scenario')}
              >
                <SlidersHorizontal size={14} /> Scenario lab
              </button>
              <span className="profile-chip">
                <i>AS</i> Analyst <ChevronDown size={13} />
              </span>
              <button className="icon-btn" aria-label="Settings">
                <Settings2 size={16} />
              </button>
            </div>
          </header>

          <div className="status-strip glass">
            <div className="status-region">
              {/* the strip's counts are landslide-risk counts; say so once, here */}
              <span className="eyebrow">
                Kangra pilot · {hazardName(region?.hazardType ?? 'landslide').toLowerCase()} risk
              </span>
              <strong>{region?.name ?? 'Kangra district'}</strong>
              <span className="status-live">
                <Radio size={10} /> ANALYSIS READY
              </span>
            </div>
            <div className="status-stat is-critical">
              <span>CRITICAL</span>
              <strong>
                <AnimatedNumber value={critical} />
              </strong>
            </div>
            <div className="status-stat">
              <span>HIGH RISK</span>
              <strong>
                <AnimatedNumber value={highRisk} />
              </strong>
            </div>
            <div className="status-stat">
              <span>EXPOSED</span>
              <strong>
                <AnimatedNumber value={exposed} format={compact} />
              </strong>
            </div>
          </div>

          <LayerPanel />

          {loaded && mode_data === 'fallback' && (
            <div className="map-caption" style={{ bottom: 112, color: 'var(--critical)' }}>
              <b style={{ color: 'var(--critical)' }}>
                <Activity size={12} /> DEVELOPMENT FIXTURE
              </b>
              <small>{dataMessage}</small>
            </div>
          )}
          <div className="map-caption">
            <b>
              <Activity size={12} /> PILOT ANALYSIS
            </b>
            <small>
              {mode_data === 'analytical'
                ? `SUSCEPTIBILITY INDEX · UNVALIDATED · ${region?.modelVersion ?? ''}`
                : 'DEVELOPMENT FIXTURE · API UNREACHABLE'}
            </small>
          </div>

          <div className="map-legend glass">
            <span className="lg-critical"><i /> Critical</span>
            <span className="lg-high"><i /> High</span>
            <span className="lg-monitor"><i /> Monitor</span>
            <span className="lg-safe"><i /> Safe</span>
          </div>

          {mode === 'regional' && (
            <motion.div
              className="map-intro"
              initial={reduced ? false : { opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            >
              <span className="eyebrow">Command centre / {region?.code ?? 'HP-KAN'}</span>
              <h1>
                See the risk
                <br />
                <em>before it moves.</em>
              </h1>
              <p>Explore the hazard, understand the vulnerability, make the next decision.</p>
              <button className="btn btn-sm btn-glass" disabled={!habitations.length}
                onClick={() => habitations[0] && focus(habitations[0])}>
                Investigate priority habitation <ArrowRight className="btn-arrow" size={14} />
              </button>
            </motion.div>
          )}

          <AnimatePresence mode="wait">
            {panel && (
              <motion.section
                key={mode}
                className={`drawer ${mode === 'executive' ? 'brief' : ''}`}
                initial={reduced ? { opacity: 0 } : { opacity: 0, x: 28 }}
                animate={{ opacity: 1, x: 0 }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, x: 22 }}
                transition={{ duration: TIMING.ui, ease: [0.16, 1, 0.3, 1] }}
              >
                {panel}
              </motion.section>
            )}
            {mode === 'scenario' && (
              <motion.section
                key="scenario"
                className="scenario-panel"
                initial={reduced ? { opacity: 0 } : { opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, y: 18 }}
                transition={{ duration: TIMING.ui, ease: [0.16, 1, 0.3, 1] }}
              >
                <ScenarioPanel running={scenarioRunning} onRun={runScenarioWithSweep} />
              </motion.section>
            )}
          </AnimatePresence>

          <footer className="console-bottom">
            <DecisionChain mode={mode} />
            <div className="bottom-actions">
              <span className="system-status">
                <i /> System nominal
              </span>
              <button className="btn btn-sm btn-accent" onClick={() => void openBrief()}>
                <FileText size={14} /> <span>Generate decision</span>
              </button>
            </div>
          </footer>
        </>
      )}
    </main>
  )
}
