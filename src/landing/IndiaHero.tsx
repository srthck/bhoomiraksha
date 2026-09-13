import { HAZARD_ANCHORS, INDIA_OUTLINE, INDIA_STATES, INDIA_VIEWBOX } from '../geo/indiaGeometry'
import { HazardSignal } from '../motion/HazardSignal'

/* Illustrative hazard belts. Colour follows the hazard family, not severity —
   severity is carried by the signal markers layered on top. */
const FIELDS = [
  { id: 'himalaya', kind: 'landslide', x: 35, y: 15, w: 48, h: 18, rot: -12 },
  { id: 'ne-flood', kind: 'flood', x: 77, y: 33, w: 20, h: 15, rot: 0 },
  { id: 'ganga', kind: 'flood', x: 60, y: 34, w: 28, h: 9, rot: -5 },
  { id: 'thar', kind: 'heat', x: 18, y: 33, w: 24, h: 22, rot: 0 },
  { id: 'bay-coast', kind: 'cyclone', x: 57, y: 55, w: 18, h: 24, rot: 0 },
  { id: 'ghats', kind: 'landslide', x: 30, y: 75, w: 13, h: 20, rot: 0 },
] as const

export default function IndiaHero() {
  return (
    <div className="india-hero" aria-hidden="true">
      <img className="india-context" src="/geo/india-context-wide.jpg" alt="" fetchPriority="high" />
      <div className="india-clouds india-clouds-back" />

      <div className="india-plate">
        <img className="india-relief" src="/geo/india-hero.png" alt="" fetchPriority="high" />

        {/* Hazard fields are masked by the relief alpha, so they stop at the coastline. */}
        <div className="india-fields">
          {FIELDS.map((f) => (
            <span
              key={f.id}
              className={`india-field field-${f.kind}`}
              style={{ left: `${f.x}%`, top: `${f.y}%`, width: `${f.w}%`, height: `${f.h}%`, rotate: `${f.rot}deg` }}
            />
          ))}
        </div>

        <svg className="india-lines" viewBox={`0 0 ${INDIA_VIEWBOX.width} ${INDIA_VIEWBOX.height}`} preserveAspectRatio="none">
          <defs>
            <filter id="coastGlow" x="-6%" y="-6%" width="112%" height="112%">
              <feGaussianBlur stdDeviation="7" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <g className="india-states">
            {INDIA_STATES.map((s) => <path key={s.name} d={s.d} />)}
          </g>
          <path className="india-coast-glow" d={INDIA_OUTLINE} filter="url(#coastGlow)" />
          <path className="india-coast" d={INDIA_OUTLINE} />
        </svg>

        <div className="india-signals">
          {HAZARD_ANCHORS.map((a) => (
            <HazardSignal key={a.id} level={a.level} kind={a.kind} label={a.label} style={{ left: `${a.x}%`, top: `${a.y}%` }} />
          ))}
        </div>
      </div>

      <div className="india-clouds india-clouds-front" />
    </div>
  )
}
