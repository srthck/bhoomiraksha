import type { CSSProperties } from 'react'
import type { HazardKind, HazardLevel } from '../geo/indiaGeometry'

const GLYPH: Record<HazardKind, string> = {
  landslide: 'M2 13 7 6l3.4 4 2.3-2.6L18 13Z',
  flood: 'M2 9c2.2-2 4.4-2 6.6 0s4.4 2 6.6 0M2 14c2.2-2 4.4-2 6.6 0s4.4 2 6.6 0',
  heat: 'M10 2c1.6 3-1.4 4.2-.2 6.6C11 11 14 11.4 14 14.2A4.4 4.4 0 0 1 6 15c0-2 1.6-2.6 1.6-4.4C7.6 8 10 6.6 10 2Z',
  cyclone: 'M10 3a7 7 0 1 1-6.4 9.8M10 7.2a3 3 0 1 1-2.6 4.4',
}

/**
 * A hazard indicator whose movement is proportional to severity: critical gets
 * an expanding ring plus a halo, high a single quiet ring, monitor a slow
 * breathe, safe nothing at all. Every animation is CSS on transform/opacity —
 * there is no timer per marker, so a map full of these stays cheap.
 */
export function HazardSignal({
  level,
  kind,
  label,
  style,
  size = 'md',
}: {
  level: HazardLevel | 'safe'
  kind?: HazardKind
  label?: string
  style?: CSSProperties
  size?: 'sm' | 'md'
}) {
  return (
    <span className={`hazard-signal sig-${level} sig-${size}`} style={style} title={label}>
      {(level === 'critical' || level === 'high') && <i className="sig-ring" />}
      {level === 'critical' && <i className="sig-ring sig-ring-2" />}
      <i className="sig-core">
        {kind && (
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d={GLYPH[kind]} fill={kind === 'landslide' ? 'currentColor' : 'none'} />
          </svg>
        )}
      </i>
      {label && <span className="sr-only">{label}</span>}
    </span>
  )
}
