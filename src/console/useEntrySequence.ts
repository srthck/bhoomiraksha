import { useEffect, useState } from 'react'
import type { MapRef } from 'react-map-gl/maplibre'
import { INDIA_CAMERA, PILOT_CAMERA } from './basemap'

/* =========================================================================
   Entry sequence: world -> rotation -> India -> pilot region -> habitations

   One MapLibre instance carries the whole journey. The globe projection
   morphs to mercator on its own as the camera descends, so there is no cut
   and no second WebGL context. Everything here is camera work; the console
   chrome and the habitation markers subscribe to `stage`.
   ========================================================================= */

export type EntryStage =
  | 'idle'      // map mounted, globe held
  | 'rotate'    // earth turns, India swings toward centre
  | 'india'     // India fills the view
  | 'descend'   // approach to the Kangra pilot region
  | 'settled'   // camera at rest, console live

/** Stage -> delay from sequence start, in ms. */
const SCHEDULE: [EntryStage, number][] = [
  ['rotate', 260],
  ['india', 1410],
  ['descend', 2110],
  ['settled', 3160],
]

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

export function useEntrySequence({
  mapRef,
  active,
  reduced,
}: {
  mapRef: React.RefObject<MapRef | null>
  active: boolean
  reduced: boolean
}) {
  const [stage, setStage] = useState<EntryStage>(active ? 'idle' : 'settled')

  useEffect(() => {
    if (!active) return

    if (reduced) {
      // no world rotation, no camera travel — go straight to the pilot region
      const map = mapRef.current?.getMap()
      try {
        map?.setProjection({ type: 'mercator' })
      } catch {
        /* style still settling; the globe projection is fine at pilot zoom */
      }
      map?.jumpTo({
        center: [PILOT_CAMERA.longitude, PILOT_CAMERA.latitude],
        zoom: PILOT_CAMERA.zoom,
        pitch: PILOT_CAMERA.pitch,
      })
      setStage('settled')
      return
    }

    const timers = SCHEDULE.map(([next, at]) =>
      window.setTimeout(() => {
        const map = mapRef.current?.getMap()
        setStage(next)
        if (!map) return

        if (next === 'rotate') {
          // spin the globe rather than cutting to India
          map.easeTo({
            center: [INDIA_CAMERA.longitude, INDIA_CAMERA.latitude],
            zoom: 2.6,
            duration: 1150,
            easing: easeInOut,
          })
        } else if (next === 'india') {
          map.flyTo({
            center: [INDIA_CAMERA.longitude, INDIA_CAMERA.latitude],
            zoom: INDIA_CAMERA.zoom,
            duration: 700,
            curve: 1.1,
            essential: true,
          })
        } else if (next === 'descend') {
          map.flyTo({
            center: [PILOT_CAMERA.longitude, PILOT_CAMERA.latitude],
            zoom: PILOT_CAMERA.zoom,
            pitch: PILOT_CAMERA.pitch,
            duration: 1050,
            curve: 1.25,
            essential: true,
          })
        } else if (next === 'settled') {
          // The globe has done its job. Drop to mercator for the working
          // session: at this zoom the two are visually identical, and deck.gl's
          // arc geometry (the allocation routes) does not render under the
          // globe projection.
          //
          // Guarded: when the remote style is unreachable the style can still
          // be settling here, and MapLibre throws "Style is not done loading".
          // The demo must not print an error just because a tile host is down.
          const apply = () => {
            try {
              map.setProjection({ type: 'mercator' })
            } catch {
              /* projection stays globe; visually identical at this zoom */
            }
          }
          if (map.isStyleLoaded()) apply()
          else map.once('idle', apply)
        }
      }, at),
    )

    return () => timers.forEach(window.clearTimeout)
  }, [active, reduced, mapRef])

  return stage
}
