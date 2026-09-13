import { useEffect, useRef, useState, type ReactNode } from 'react'
import { motion, type Transition } from 'framer-motion'

/* =========================================================================
   Motion primitives
   One timing scale and one set of components for the whole product, so the
   landing, the map and every panel move at the same speeds. Looping hazard
   signals are pure CSS (see hazard.css) — never a React timer per point.
   ========================================================================= */

export const TIMING = {
  micro: 0.14,   // hover, press, toggle
  ui: 0.32,      // panel and control entry
  cinematic: 0.82, // decision transitions
  camera: 1.05,  // map fly-to
} as const

export const EASE_OUT = [0.16, 1, 0.3, 1] as const
export const EASE = [0.22, 0.75, 0.24, 1] as const

export const uiTransition: Transition = { duration: TIMING.ui, ease: EASE_OUT }
export const cineTransition: Transition = { duration: TIMING.cinematic, ease: EASE_OUT }

/** Live-updating reduced-motion preference. */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/**
 * Counts to `value` on a single rAF loop. Reduced motion snaps to the value so
 * the number is still correct without the count-up.
 */
const defaultFormat = (n: number) => Math.round(n).toLocaleString('en-IN')

export function AnimatedNumber({
  value,
  duration = 900,
  delay = 0,
  format = defaultFormat,
}: {
  value: number
  duration?: number
  delay?: number
  format?: (n: number) => string
}) {
  const reduced = useReducedMotion()
  const node = useRef<HTMLSpanElement>(null)
  const from = useRef(reduced ? value : 0)

  // The count-up writes straight to the text node. Driving it through React
  // state would re-render this component's whole subtree once per frame, and
  // three of these run while the camera is still settling into the region.
  useEffect(() => {
    const el = node.current
    if (!el) return
    const start = from.current
    const delta = value - start

    if (reduced || delta === 0) {
      from.current = value
      el.textContent = format(value)
      return
    }

    let frame = 0
    const begin = performance.now() + delay
    const tick = (now: number) => {
      const p = Math.min(1, Math.max(0, (now - begin) / duration))
      const eased = 1 - Math.pow(1 - p, 3)
      const next = start + delta * eased
      from.current = next
      el.textContent = format(next)
      if (p < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, duration, delay, reduced, format])

  return (
    <span ref={node} className="mono tabular">
      {format(from.current)}
    </span>
  )
}

export const compact = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}K` : Math.round(n).toString())

/**
 * Staggered entry used by the landing sequence and panel contents. `step` is
 * the index in a reveal group; `base`/`gap` are milliseconds.
 */
export function Reveal({
  children,
  step = 0,
  base = 0,
  gap = 90,
  y = 16,
  className,
  as = 'div',
}: {
  children: ReactNode
  step?: number
  base?: number
  gap?: number
  y?: number
  className?: string
  as?: 'div' | 'section' | 'header' | 'footer' | 'li'
}) {
  const reduced = useReducedMotion()
  const Tag = motion[as]
  return (
    <Tag
      className={className}
      initial={reduced ? { opacity: 1 } : { opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? { duration: 0 } : { duration: 0.7, delay: (base + step * gap) / 1000, ease: EASE_OUT }}
    >
      {children}
    </Tag>
  )
}

/** Right drawer / bottom sheet entry. Direction is handled in CSS by breakpoint. */
export function PanelReveal({ children, className, panelKey }: { children: ReactNode; className?: string; panelKey?: string }) {
  const reduced = useReducedMotion()
  return (
    <motion.section
      key={panelKey}
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, x: 26 }}
      animate={{ opacity: 1, x: 0 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, x: 20 }}
      transition={{ duration: TIMING.ui, ease: EASE_OUT }}
    >
      {children}
    </motion.section>
  )
}

/**
 * A bar that grows from 0 to `pct` once. Purely CSS-transformed so a stack of
 * these costs nothing on the compositor.
 */
export function GrowBar({ pct, delay = 0, className = '', tone }: { pct: number; delay?: number; className?: string; tone?: string }) {
  const reduced = useReducedMotion()
  return (
    <span className={`growbar ${className}`}>
      <motion.i
        style={tone ? { background: tone } : undefined}
        initial={reduced ? { scaleX: pct / 100 } : { scaleX: 0 }}
        animate={{ scaleX: pct / 100 }}
        transition={reduced ? { duration: 0 } : { duration: 0.85, delay: delay / 1000, ease: EASE_OUT }}
      />
    </span>
  )
}
