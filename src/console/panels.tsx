import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, Check, Info, MapPin, Route, Sparkles, Target, X } from 'lucide-react'
import type { ApiHazardModel, ApiScenario } from '../data/api'
import type { ConsoleHabitation, ConsoleSite } from '../data/provider'
import { displayRisk, hazardName, riskIndexLabel, susceptibilityLabel } from '../data/hazards'
import { useConsoleStore } from '../store/consoleStore'
import { AnimatedNumber, EASE_OUT, GrowBar, Reveal, useReducedMotion } from '../motion/primitives'

/* ---------------------------------------------------------------- shared -- */

export function DrawerClose({ onClick }: { onClick: () => void }) {
  return (
    <button className="drawer-close" onClick={onClick} aria-label="Close panel">
      <X size={16} />
    </button>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="section">
      <span className="eyebrow">{title}</span>
      {children}
    </div>
  )
}

function RiskDial({ value, label }: { value: number; label: string }) {
  const reduced = useReducedMotion()
  const c = 2 * Math.PI * 33
  return (
    <div className="risk-dial">
      <svg viewBox="0 0 76 76" aria-hidden="true">
        <circle className="track" cx="38" cy="38" r="33" />
        <motion.circle
          className="value"
          cx="38"
          cy="38"
          r="33"
          strokeDasharray={c}
          initial={{ strokeDashoffset: reduced ? c * (1 - value / 100) : c }}
          animate={{ strokeDashoffset: c * (1 - value / 100) }}
          transition={{ duration: reduced ? 0 : 1, delay: reduced ? 0 : 0.2, ease: EASE_OUT }}
        />
      </svg>
      <span>{label}</span>
    </div>
  )
}

const num = (v: number | null | undefined) => (v ?? 0).toLocaleString('en-IN')
const one = (n: number) => n.toFixed(1)

/** The model that produced a settlement's score: its own detail first, then the region's. */
function useHazardModel(h: ConsoleHabitation | null): ApiHazardModel | null {
  const regionModel = useConsoleStore((s) => s.region?.hazardModel ?? null)
  return h?.detail?.hazard_model ?? regionModel
}

const RISK_MEANING_FALLBACK =
  'Composite risk score from hazard susceptibility, exposure, vulnerability and response difficulty. ' +
  'A decision-support index, not the probability of a landslide occurring.'

/** Small keyboard-reachable explanation. Concise by design; no modal, no card. */
function InfoTip({ text }: { text: string }) {
  return (
    <button type="button" className="info-tip" aria-label={text} data-tip={text}>
      <Info size={11} aria-hidden="true" />
    </button>
  )
}

/** Component order the methodology is written in, not sorted by size. */
const COMPONENT_ORDER = ['hazard', 'exposure', 'vulnerability', 'response'] as const

/* ---------------------------------------------------------- investigate -- */

export function HabitationPanel({ habitation }: { habitation: ConsoleHabitation }) {
  const setMode = useConsoleStore((s) => s.setMode)
  const model = useHazardModel(habitation)
  return (
    <>
      <DrawerClose onClick={() => setMode('regional')} />
      <Reveal step={0} gap={70}>
        <span className={`tag tag-${habitation.level === 'critical' || habitation.level === 'high' ? 'critical' : 'safe'}`}>
          <i />
          {habitation.level} {hazardName(habitation.hazardType).toLowerCase()} risk · priority #{habitation.priorityRank}
        </span>
        <h2>{habitation.name}</h2>
        <p className="muted">{habitation.district}</p>
      </Reveal>

      <Reveal step={1} gap={70}>
        <div className="risk-block">
          <div className="risk-value">
            <span className="eyebrow risk-label">
              {riskIndexLabel(habitation.hazardType)}
              <InfoTip text={model?.meaning ?? RISK_MEANING_FALLBACK} />
            </span>
            <strong>
              <AnimatedNumber value={habitation.risk} duration={900} delay={140} />
              <small className="risk-scale">/ 100</small>
            </strong>
            <span className={`risk-class is-${habitation.level}`}>{habitation.level}</span>
            <small className="risk-basis">
              {model
                ? `Hazard model: ${model.model_name} · ${model.assessment}`
                : 'Development fixture · no hazard model ran'}
            </small>
          </div>
          <RiskDial value={habitation.risk} label={habitation.recommendation} />
        </div>
      </Reveal>

      <Reveal step={2} gap={70}>
        <div className="metric-grid">
          <Metric label="Population (GHSL est.)" value={num(habitation.population)} />
          <Metric label="Exposed population" value={num(habitation.exposedPopulation)} />
          <Metric label="Exposed area" value={`${habitation.exposedAreaPercent.toFixed(0)}%`} />
          <Metric
            label={susceptibilityLabel(habitation.hazardType)}
            value={`${habitation.meanHazard.toFixed(0)} mean · ${habitation.maxHazard.toFixed(0)} peak`}
          />
          <Metric label="Vulnerability (proxy)" value={habitation.vulnerability} />
          <Metric label="Response difficulty" value={habitation.accessibility} />
        </div>
      </Reveal>

      <Reveal step={3} gap={70}>
        <Section title="Why it matters">
          {habitation.factors.slice(0, 4).map((f) => (
            <div className="reason" key={f.id}>
              <i>+</i>
              <span>{f.evidence}</span>
            </div>
          ))}
        </Section>
      </Reveal>

      <Reveal step={4} gap={70}>
        <Section title="What next?">
          <div className="drawer-actions">
            <button className="btn btn-sm btn-glass btn-block" onClick={() => setMode('explain')}>
              Investigate why <ArrowRight className="btn-arrow" size={14} />
            </button>
            <button className="btn btn-sm btn-accent btn-block" onClick={() => setMode('relocation')}>
              Assess relocation <Route size={14} />
            </button>
          </div>
        </Section>
        <p className="note">
          Data confidence {habitation.confidence}. Susceptibility is an unvalidated index, not a prediction.
        </p>
      </Reveal>
    </>
  )
}

/* --------------------------------------------------------------- explain -- */

export function ExplainPanel({ habitation }: { habitation: ConsoleHabitation }) {
  const setMode = useConsoleStore((s) => s.setMode)
  const detail = habitation.detail
  const model = useHazardModel(habitation)
  const type = habitation.hazardType
  const byId = new Map((detail?.explanation.contributions ?? []).map((c) => [c.id, c]))
  const rows = COMPONENT_ORDER.map((id) => byId.get(id)).filter((c) => c !== undefined)
  const total = detail?.explanation.total ?? habitation.risk
  const shown = detail?.risk_display ?? displayRisk(habitation.risk)
  const mean = detail?.hazard.mean_susceptibility ?? habitation.meanHazard
  const peak = detail?.hazard.peak_susceptibility ?? habitation.maxHazard

  return (
    <>
      <DrawerClose onClick={() => setMode('investigate')} />
      <span className="eyebrow">Why this score? / {habitation.name}</span>
      <div className="explain-score">
        <span className="eyebrow">{riskIndexLabel(type)}</span>
        <strong>
          <AnimatedNumber value={total} duration={800} format={one} />
        </strong>
        <small className="eyebrow">Displayed as {shown} / 100 · decision-support index, not a probability</small>
      </div>

      <p className="explain-gap">
        Mean {susceptibilityLabel(type).toLowerCase()} is <b>{one(mean)} / 100</b>. The risk index is a
        composite: it also weighs exposure, vulnerability and response difficulty, which is why it reads{' '}
        <b>{one(total)}</b>.
      </p>

      <Section title="Why this score? — transparent weighted contribution">
        {rows.length === 0 && <div className="empty">Loading the contribution breakdown…</div>}
        {rows.map((c, i) => (
          <div className="factor" key={c.id}>
            <div>
              <span>{c.label}</span>
              <b>
                {one(c.component_score)} × {Math.round(c.weight * 100)}% = {one(c.contribution)}
              </b>
            </div>
            <GrowBar pct={(c.contribution / Math.max(total, 1)) * 100} delay={180 + i * 130} />
            <small>{c.evidence}</small>
          </div>
        ))}
        {rows.length > 0 && (
          <div className="factor-total">
            <span>Total</span>
            <b>
              {one(total)} → displayed {shown}
            </b>
          </div>
        )}
      </Section>

      {model && (
        <Section title={`Hazard basis — ${model.susceptibility_label.toLowerCase()} model`}>
          {model.basis.map((b) => (
            <div className="basis-row" key={b.factor}>
              <span>{b.label}</span>
              <b>{Math.round(b.weight * 100)}%</b>
            </div>
          ))}
          <small className="basis-note">
            Share of the susceptibility index per factor — not model accuracy, not probability.
            {model.validated ? '' : ' Unvalidated: no landslide inventory was available for Kangra.'}
          </small>
          <div className="metric-grid" style={{ marginTop: 12 }}>
            <Metric label="Mean susceptibility" value={`${one(mean)} / 100`} />
            <Metric label="Peak susceptibility" value={`${one(peak)} / 100`} />
          </div>
          {detail && (
            <p className="formula">
              Hazard = {model.hazard_mean_weight} × {one(mean)} + {model.hazard_peak_weight} × {one(peak)} ={' '}
              {one(detail.hazard.hazard_component)}
            </p>
          )}
        </Section>
      )}

      <Section title="What next?">
        <button className="btn btn-sm btn-accent btn-block" onClick={() => setMode('relocation')}>
          Assess relocation <ArrowRight className="btn-arrow" size={14} />
        </button>
      </Section>
      <p className="note">
        {detail?.explanation.note ??
          'Each factor score multiplied by its documented weight; contributions sum to the risk score. Not SHAP.'}
      </p>
    </>
  )
}

/* ------------------------------------------------------------ relocation -- */

export function RelocationPanel({
  habitation,
  selectedSite,
}: {
  habitation: ConsoleHabitation | null
  selectedSite: ConsoleSite | null
}) {
  const { setMode, selectSite, sites, sitesLoading } = useConsoleStore()
  return (
    <>
      <DrawerClose onClick={() => setMode(habitation ? 'investigate' : 'regional')} />
      <span className="tag tag-safe">
        <i />
        Solution discovery
      </span>
      <h2>Find a safe destination</h2>
      <p className="muted">
        Source: {habitation?.name ?? 'No habitation selected'}
        {habitation ? ` · ${num(habitation.exposedPopulation)} people to relocate` : ''}
      </p>

      <Section title="Candidate sites">
        {sitesLoading && <div className="empty">Screening the land surface…</div>}
        {!sitesLoading && sites.length === 0 && (
          <div className="empty">No candidate site passed screening within range.</div>
        )}
        {sites.map((site, i) => (
          <Reveal key={site.id} step={i} base={120} gap={110} y={10}>
            <button
              className={`site-row ${selectedSite?.id === site.id ? 'is-selected' : ''}`}
              onClick={() => void selectSite(site)}
            >
              <i>
                <MapPin size={14} />
              </i>
              <span>
                <strong>{site.name}</strong>
                <small>
                  {site.screeningStatus} · suitability {site.suitability.toFixed(0)}
                  {site.distanceKm != null ? ` · ${site.distanceKm.toFixed(1)} km` : ''} ·{' '}
                  {num(site.availableCapacity)} available
                </small>
              </span>
              <ArrowRight size={14} />
            </button>
          </Reveal>
        ))}
      </Section>

      <p className="note">
        <Target size={11} style={{ display: 'inline', verticalAlign: -1, marginRight: 5 }} />
        Preliminary candidate land: screened patches of Kangra that passed a spatial screen on
        susceptibility, slope, elevation, existing occupation and watercourses, ranked on safety,
        terrain, road and healthcare access. Ownership and land use have not been verified.
      </p>
    </>
  )
}

/* -------------------------------------------------------------- capacity -- */

const CONSTRAINT_ORDER = ['land', 'healthcare', 'environment', 'infrastructure', 'accessibility'] as const

export function CapacityPanel({ site, habitation }: { site: ConsoleSite; habitation: ConsoleHabitation | null }) {
  const { setMode, runOptimization, optimizationRunning } = useConsoleStore()
  const caps = site.capacity
  // Use the engine's own figures. Recomputing them in the browser from rounded
  // constraint values drifted by a person against the optimisation input.
  const effective = site.effectiveCapacity
  const available = site.availableCapacity
  const demand = habitation?.exposedPopulation ?? 0
  const fits = habitation ? available >= demand : false
  const scale = Math.max(...Object.values(caps), 1)
  const stackMs = CONSTRAINT_ORDER.length * 130

  return (
    <>
      <DrawerClose onClick={() => setMode('relocation')} />
      <span className="eyebrow">Site intelligence / {site.name}</span>
      <h2>Carrying capacity</h2>
      <p className="muted">
        Evaluating {habitation?.name ?? 'the selected habitation'} · {site.areaKm2.toFixed(2)} km² screened candidate area
      </p>

      <Section title="Constraint stack">
        {CONSTRAINT_ORDER.map((key, i) => (
          <div className={`constraint ${key === site.bindingConstraint ? 'is-binding' : ''}`} key={key}>
            <div>
              <span>{key}</span>
              <b>
                <AnimatedNumber value={caps[key]} duration={780} delay={i * 130} />
              </b>
            </div>
            <GrowBar pct={(caps[key] / scale) * 100} delay={i * 130} />
            {key === site.bindingConstraint && <small>Binding limit</small>}
          </div>
        ))}
      </Section>

      <Reveal base={stackMs + 120} y={10}>
        <div className="metric-grid" style={{ marginTop: 20 }}>
          <Metric label="Effective capacity" value={num(effective)} />
          <Metric label="Current population" value={num(site.currentPopulation)} />
        </div>
      </Reveal>

      <Reveal base={stackMs + 320} y={10}>
        <div className="metric-grid" style={{ marginTop: 1, gridTemplateColumns: '1fr' }}>
          <Metric label="Available capacity" value={num(available)} />
        </div>
      </Reveal>

      <Reveal base={stackMs + 560} y={10}>
        <div className={`capacity-verdict ${fits ? '' : 'is-fail'}`}>
          {fits ? <Check size={16} /> : <X size={16} />}
          <span>
            {habitation
              ? `${site.name} ${fits ? 'can accommodate' : 'cannot fully accommodate'} ${habitation.name}'s ${num(demand)} exposed residents`
              : 'Select a habitation to validate capacity'}
          </span>
        </div>
      </Reveal>

      <Reveal base={stackMs + 700} y={10}>
        <div className="drawer-actions">
          <button
            className="btn btn-sm btn-accent btn-block"
            onClick={() => void runOptimization()}
            disabled={!habitation || optimizationRunning}
          >
            {optimizationRunning ? 'Solving…' : 'Optimise allocation'} <ArrowRight className="btn-arrow" size={14} />
          </button>
        </div>
      </Reveal>
      <p className="note">
        Effective capacity is the binding minimum across the five constraints, not their sum. Land is
        derived from the slope raster; the environmental limit is a water availability proxy from the
        rainfall raster; healthcare uses mapped facilities and IPHS norms; infrastructure and
        accessibility ceilings are documented pilot assumptions scaled by measured road distance.
      </p>
    </>
  )
}

/* ---------------------------------------------------------- optimization -- */

export function OptimizationPanel({
  habitation,
  revealed,
}: {
  habitation: ConsoleHabitation | null
  revealed: number
}) {
  const { optimizationResult, optimizationRunning, setMode } = useConsoleStore()
  const status = optimizationResult?.solver_status
  return (
    <>
      <DrawerClose onClick={() => setMode('capacity')} />
      <span className="tag tag-safe">
        <i />
        {optimizationRunning ? 'Solving' : `Solver ${status ?? 'ready'}`}
      </span>
      <h2>Constrained allocation</h2>
      <p className="muted">
        OR-Tools allocation for {habitation?.name ?? 'priority habitations'}
        {optimizationResult ? ` · ${optimizationResult.sinks} eligible sites` : ''}
      </p>

      {optimizationRunning && <div className="empty">Running the constrained solver…</div>}

      {!optimizationRunning && optimizationResult && (
        <>
          <Section title="Assignments">
            {optimizationResult.allocations.slice(0, revealed).map((a) => (
              <Reveal key={`${a.source_id}-${a.site_id}`} y={8} gap={0}>
                <div className="alloc-row">
                  <span>
                    <strong>{a.source_name}</strong>
                    <small>{num(a.population)} residents</small>
                  </span>
                  <ArrowRight size={14} />
                  <span>
                    <strong>{a.site_id.replace('cand-', 'Site ')}</strong>
                    <small>
                      {a.distance_km.toFixed(1)} km · suitability {a.site_suitability.toFixed(0)}
                    </small>
                  </span>
                </div>
              </Reveal>
            ))}
          </Section>

          {revealed >= optimizationResult.allocations.length && (
            <Reveal y={10}>
              <div className="constraint-chips">
                {optimizationResult.constraint_summary.map((c) => (
                  <span key={c}>
                    <Check size={11} /> {c}
                  </span>
                ))}
              </div>
              <div className="metric-grid" style={{ marginTop: 14 }}>
                <Metric label="Relocated" value={num(optimizationResult.total_relocated)} />
                <Metric label="Unallocated" value={num(optimizationResult.unallocated_population)} />
              </div>
              <div className="decision-status">
                <span className="eyebrow">Solver result</span>
                <strong>
                  {status === 'OPTIMAL'
                    ? 'Optimal allocation'
                    : status === 'FEASIBLE'
                      ? 'Feasible allocation (time limit reached)'
                      : `Solver reported ${status}`}
                </strong>
              </div>
              <div className="drawer-actions">
                <button className="btn btn-sm btn-glass btn-block" onClick={() => setMode('scenario')}>
                  Open scenario lab <ArrowRight className="btn-arrow" size={14} />
                </button>
              </div>
              <p className="note">Objective: {optimizationResult.objective_description}</p>
            </Reveal>
          )}
        </>
      )}

      {!optimizationRunning && !optimizationResult && (
        <div className="empty">Run the allocation from the capacity panel to see assignments.</div>
      )}
    </>
  )
}

/* -------------------------------------------------------------- scenario -- */

function Slider({
  label,
  value,
  suffix,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  suffix: string
  min: number
  max: number
  onChange: (v: number) => void
}) {
  return (
    <label className="slider-row">
      <span>
        {label}
        <b>
          {value}
          {suffix}
        </b>
      </span>
      <input type="range" value={value} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

export function ScenarioPanel({ running, onRun }: { running: boolean; onRun: () => void }) {
  const { scenarioParameters, scenarioResult, setScenarioParameter, setMode } = useConsoleStore()
  const step = scenarioResult ? 3 : running ? 2 : 1

  return (
    <>
      <div className="scenario-head">
        <div>
          <span className="eyebrow">Scenario lab / pipeline re-run</span>
          <h2>Stress-test the region</h2>
        </div>
        <DrawerClose onClick={() => setMode('regional')} />
      </div>

      <div className="scenario-steps">
        {['01 Baseline', '02 Conditions', '03 Simulate', '04 Compare'].map((s, i) => (
          <span key={s} className={i <= step ? 'on' : ''}>
            {s}
          </span>
        ))}
      </div>

      <Slider label="Rainfall" value={scenarioParameters.rainfall} suffix="%" min={0} max={50} onChange={(v) => setScenarioParameter('rainfall', v)} />
      <Slider label="Road availability" value={scenarioParameters.roads} suffix="%" min={50} max={100} onChange={(v) => setScenarioParameter('roads', v)} />
      <Slider label="Population load" value={scenarioParameters.population} suffix="%" min={0} max={30} onChange={(v) => setScenarioParameter('population', v)} />

      <button className="btn btn-sm btn-accent btn-block" onClick={onRun} disabled={running} style={{ marginTop: 18 }}>
        <Sparkles size={14} /> {running ? 'Recomputing the pipeline…' : 'Run scenario'}
      </button>

      {scenarioResult ? (
        <Reveal y={12}>
          <span className="eyebrow" style={{ display: 'block', marginTop: 20 }}>
            Baseline vs scenario · {scenarioResult.runtime_ms} ms
          </span>
          <div className="impact-grid">
            {scenarioResult.deltas.slice(0, 3).map((d) => (
              <Impact key={d.label} label={d.label} before={d.baseline} after={d.scenario} />
            ))}
          </div>
          <div className="impact-grid" style={{ marginTop: 1 }}>
            {scenarioResult.deltas.slice(3).map((d) => (
              <Impact key={d.label} label={d.label} before={d.baseline} after={d.scenario} />
            ))}
          </div>
          {scenarioResult.changed_habitations.length > 0 && (
            <Section title="Reclassified habitations">
              {scenarioResult.changed_habitations.slice(0, 5).map((c) => (
                <div className="reason" key={c.id}>
                  <i>→</i>
                  <span>
                    {c.name}: {c.from} → <b>{c.to}</b> (risk {c.risk_baseline} → {c.risk_scenario})
                  </span>
                </div>
              ))}
            </Section>
          )}
          <p className="note">
            {scenarioResult.propagation_notes.join('. ')}. Solver re-run:{' '}
            {scenarioResult.optimization.solver_status}.
          </p>
        </Reveal>
      ) : (
        <div className="empty">
          Adjust the conditions, then run the scenario. Rainfall and population re-enter the
          susceptibility and exposure calculations and the whole chain is recomputed.
        </div>
      )}
    </>
  )
}

function Impact({ label, before, after }: { label: string; before: number; after: number }) {
  const fmt = (n: number) => (Math.abs(n) >= 10000 ? `${(n / 1000).toFixed(1)}K` : Math.round(n).toLocaleString('en-IN'))
  const delta = after - before
  return (
    <div className="impact">
      <span>{label}</span>
      <strong>
        {fmt(before)} <i>→</i> <u>{fmt(after)}</u>
      </strong>
      <small>
        {delta >= 0 ? '+' : '−'}
        {fmt(Math.abs(delta))}
      </small>
    </div>
  )
}

/* ------------------------------------------------------- executive brief -- */

export function ExecutiveBrief({ habitation }: { habitation: ConsoleHabitation | null; site: ConsoleSite | null }) {
  const { setMode, brief } = useConsoleStore()
  const subject = brief?.habitation
  const name = subject?.name ?? habitation?.name ?? '—'

  return (
    <>
      <DrawerClose onClick={() => setMode('regional')} />
      <Reveal step={0} gap={110}>
        <div className="brief-brand">
          BHOOMI <span>RAKSHA</span>
        </div>
      </Reveal>

      <Reveal step={1} gap={110}>
        <span className="eyebrow" style={{ display: 'block', marginTop: 22 }}>
          Regional risk brief / {brief?.region ?? 'Kangra district'}
        </span>
        <h2>Decision required</h2>
      </Reveal>

      {!brief && <div className="empty">Preparing the decision brief…</div>}

      {brief && (
        <>
          <Reveal step={2} gap={110}>
            <div className="brief-hero">
              <span className="eyebrow">Top priority · rank #{subject?.priority_rank}</span>
              <strong>{name}</strong>
              <p>
                {String(brief.recommended.action)} recommended — {brief.index_label.toLowerCase()}{' '}
                {subject?.risk_score} / 100 ({subject?.level}), a decision-support index, not a probability.{' '}
                {num(subject?.exposed_population)} of an estimated {num(subject?.population)} residents are in
                High or Very High {hazardName(brief.hazard_type).toLowerCase()} susceptibility terrain.
              </p>
            </div>
          </Reveal>

          <Reveal step={3} gap={110}>
            <Section title="Observed / sourced">
              <div className="metric-grid">
                <Metric label="Population (GHSL estimate)" value={num(Number(brief.observed.population_estimate))} />
                <Metric label="Site slope" value={`${Number(brief.observed.site_slope_deg ?? 0).toFixed(0)}°`} />
                <Metric label="To major road" value={`${Number(brief.observed.distance_to_major_road_km ?? 0).toFixed(1)} km`} />
                <Metric label="To health care" value={`${Number(brief.observed.distance_to_health_km ?? 0).toFixed(1)} km`} />
              </div>
            </Section>
          </Reveal>

          <Reveal step={4} gap={110}>
            <Section title="Derived">
              <div className="metric-grid">
                <Metric label={susceptibilityLabel(brief.hazard_type)} value={`${String(brief.derived.mean_susceptibility)} / 100`} />
                <Metric label="Exposed area" value={`${Number(brief.derived.exposed_area_percent ?? 0).toFixed(0)}%`} />
                <Metric label={brief.index_label} value={`${String(brief.derived.risk_display ?? brief.derived.risk_score)} / 100`} />
                <Metric label="Risk class" value={String(brief.derived.risk_class)} />
              </div>
            </Section>
          </Reveal>

          <Reveal step={5} gap={110}>
            <Section title="Recommended">
              <div className="metric-grid">
                <Metric label="Preferred site" value={String(brief.recommended.preferred_site ?? '—').replace('cand-', 'Site ')} />
                <Metric label="Available capacity" value={num(Number(brief.recommended.available_capacity ?? 0))} />
                <Metric label="Binding constraint" value={String(brief.recommended.binding_constraint ?? '—')} />
                <Metric label="Relocation demand" value={num(Number(brief.recommended.relocation_demand ?? 0))} />
              </div>
              {brief.optimization && (
                <div className="decision-status" style={{ marginTop: 14 }}>
                  <span className="eyebrow">Solver</span>
                  <strong>
                    {brief.optimization.solver_status} · {num(brief.optimization.total_relocated)} placed,{' '}
                    {num(brief.optimization.unallocated_population)} unallocated
                  </strong>
                </div>
              )}
            </Section>
          </Reveal>

          <Reveal step={6} gap={110}>
            <Section title="Why">
              {(brief.derived.contributions
                ? Object.entries(brief.derived.contributions as Record<string, number>)
                : []
              ).map(([k, v]) => (
                <div className="reason" key={k}>
                  <i>+</i>
                  <span>
                    {k} — {v.toFixed(1)} of {subject?.risk_score}
                  </span>
                </div>
              ))}
            </Section>
          </Reveal>

          <Reveal step={7} gap={110}>
            <div className="decision-status">
              <span className="eyebrow">Data confidence</span>
              <strong>{brief.data_confidence}</strong>
            </div>
            <Section title="Because">
              {brief.confidence_reasons.map((r) => (
                <div className="reason" key={r}>
                  <i>·</i>
                  <span>{r}</span>
                </div>
              ))}
            </Section>
            <p className="note">
              {brief.disclaimer} Generated {new Date(brief.generated_at).toLocaleString('en-IN')} · model{' '}
              {brief.model_version}.
            </p>
          </Reveal>
        </>
      )}
    </>
  )
}

export type { ApiScenario }
