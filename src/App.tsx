import { useCallback, useEffect, useState } from 'react'
import Landing from './landing/Landing'
import CommandCenter from './console/CommandCenter'
import { useReducedMotion } from './motion/primitives'
import './styles/base.css'
import './styles/hazard.css'

/**
 * `approach` is the window in which both surfaces exist: the console's map is
 * already mounted and flying from the globe toward the pilot region while the
 * landing dissolves over it. Crossfading rather than swapping is what keeps
 * the geography continuous — there is never a blank frame between them.
 */
type Phase = 'landing' | 'approach' | 'console'

export default function App() {
  const reduced = useReducedMotion()
  const [phase, setPhase] = useState<Phase>('landing')

  const enter = useCallback(() => setPhase((p) => (p === 'landing' ? 'approach' : p)), [])

  useEffect(() => {
    if (phase !== 'approach') return
    // the landing layer is fully transparent well before this; unmounting it
    // here frees its rasters once the camera has committed to the descent
    // landing-out finishes at 900ms; holding a fully transparent full-screen
    // layer (masks, blurs, a scaling raster subtree) on top of the globe for
    // another 600ms was pure compositing cost with nothing on screen to show
    const t = window.setTimeout(() => setPhase('console'), reduced ? 260 : 950)
    return () => window.clearTimeout(t)
  }, [phase, reduced])

  return (
    <>
      {/* `arriving` is fixed for the life of the mount: the console runs its
          entry sequence once and must not have it cancelled when the landing
          finally unmounts. */}
      {phase !== 'landing' && <CommandCenter arriving />}
      {phase !== 'console' && <Landing onEnter={enter} leaving={phase === 'approach'} />}
    </>
  )
}
