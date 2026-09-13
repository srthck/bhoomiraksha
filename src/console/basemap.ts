import type { LayerSpecification, StyleSpecification } from 'maplibre-gl'

/* =========================================================================
   Basemap composition

   The geographic surface is built from local assets first and enriched with a
   remote vector style only if that style is reachable:

     background      deep charcoal, so nothing is ever a black void
     earth           local Blue Marble pyramid, carries the globe phase
     pilot relief    local hillshade of the Kangra pilot region
     remote detail   roads, water, boundaries and labels, when available

   If the remote style cannot be fetched the map still renders real terrain at
   every zoom the product uses. That is the whole point — the console must not
   depend on a demo tile endpoint to look like a map.
   ========================================================================= */

export const REMOTE_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'

/** Written by scripts/pilot_relief.py — keep in sync with its BOUNDS output. */
export const PILOT_RELIEF_BOUNDS = {
  west: 73.828125,
  east: 79.101562,
  north: 34.597042,
  south: 29.535230,
}

export const PILOT_CAMERA = { longitude: 76.39, latitude: 32.17, zoom: 9.6, pitch: 34, bearing: 0 }

/** Where the globe starts: India is off to the right, so the spin has somewhere
 *  to go, and the sphere already fills the frame rather than floating in it. */
export const GLOBE_START = { longitude: -14, latitude: 20, zoom: 1.85, pitch: 0, bearing: 0 }
export const INDIA_CAMERA = { longitude: 79.5, latitude: 22.4, zoom: 3.9 }

let remoteStylePromise: Promise<StyleSpecification | null> | null = null

/** Warm the remote style while the user is still reading the landing page. */
export function prefetchRemoteStyle(): Promise<StyleSpecification | null> {
  if (!remoteStylePromise) {
    // a hung request must not hold up the entry sequence — fall back to local
    remoteStylePromise = Promise.race([
      fetch(REMOTE_STYLE_URL).then((r) => (r.ok ? (r.json() as Promise<StyleSpecification>) : null)),
      new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 4000)),
    ]).catch(() => null)
  }
  return remoteStylePromise
}

let earthWarmed = false

/**
 * Decode the low zoom Earth tiles up front. Without this the globe's first
 * frames are an untextured sphere, which is the one moment of the entry
 * sequence the user cannot look away from.
 */
export function prefetchEarth() {
  if (earthWarmed) return
  earthWarmed = true

  // The pilot relief is a single 2048px texture that MapLibre decodes and
  // uploads when the style loads. Left alone that decode lands in the middle
  // of the descent; decoding it here puts it in the cache while the visitor
  // is still on the landing page.
  const relief = new Image()
  relief.decoding = 'async'
  relief.src = '/geo/pilot-relief.jpg'
  void relief.decode?.().catch(() => {})

  for (let z = 0; z <= 2; z++) {
    const n = 1 << z
    for (let x = 0; x < n; x++) {
      for (let y = 0; y < n; y++) {
        const img = new Image()
        img.decoding = 'async'
        img.src = `/geo/earth/${z}/${x}/${y}.jpg`
      }
    }
  }
}

/**
 * Remote layers we keep. Fills are excluded because the style's landcover and
 * background polygons would paint over the terrain relief — except water,
 * which we want back for lakes and rivers. Buildings, land use and points of
 * interest are noise at the zooms this product works at.
 */
const DROP = /building|landuse|landcover|poi|park|aeroway|golf|pitch|cemetery|hospital-icon/i

function keepRemoteLayer(layer: LayerSpecification): boolean {
  if (layer.type === 'background' || layer.type === 'raster') return false
  if (DROP.test(layer.id)) return false
  if (layer.type === 'fill' || layer.type === 'fill-extrusion') {
    const sourceLayer = 'source-layer' in layer ? String(layer['source-layer'] ?? '') : ''
    return /water|ocean|river/i.test(sourceLayer) || /water|ocean|river/i.test(layer.id)
  }
  return true
}

/**
 * The remote style is designed for a light background. Over the terrain
 * relief its roads and labels read far too loudly and compete with the hazard
 * palette, so they are damped to a supporting role: roads become faint
 * graphite lines, water sits dark, labels go quiet grey.
 */
function dampRemoteLayer(layer: LayerSpecification): LayerSpecification {
  const paint = { ...(('paint' in layer ? layer.paint : undefined) ?? {}) } as Record<string, unknown>

  if (layer.type === 'line') {
    paint['line-opacity'] = /motorway|trunk|primary|rail/i.test(layer.id) ? 0.5 : 0.28
    paint['line-color'] = /rail/i.test(layer.id) ? '#7d8a85' : '#c9d2cc'
  } else if (layer.type === 'fill') {
    paint['fill-color'] = '#0d2b3a'
    paint['fill-opacity'] = 0.72
  } else if (layer.type === 'symbol') {
    paint['text-color'] = '#c2ccc6'
    paint['text-halo-color'] = 'rgba(6,12,15,0.9)'
    paint['text-halo-width'] = 1.3
    paint['icon-opacity'] = 0.55
  }

  return { ...layer, paint } as LayerSpecification
}

export function buildMapStyle(remote: StyleSpecification | null): StyleSpecification {
  const { west, east, north, south } = PILOT_RELIEF_BOUNDS

  const style: StyleSpecification = {
    version: 8,
    // globe below ~z6, mercator above: MapLibre interpolates the projection for us
    projection: { type: 'globe' },
    sky: {
      'sky-color': '#0f3a63',
      'sky-horizon-blend': 0.6,
      'horizon-color': '#8fc4de',
      'horizon-fog-blend': 0.55,
      'fog-color': '#0a1c26',
      'fog-ground-blend': 0.7,
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 0.7, 8, 0],
    },
    // Only include these when the remote style supplied them: MapLibre's
    // validator rejects an explicit `glyphs: undefined` and logs an error when
    // the remote basemap is slow or unreachable.
    ...(remote?.glyphs ? { glyphs: remote.glyphs } : {}),
    ...(remote?.sprite ? { sprite: remote.sprite } : {}),
    sources: {
      earth: {
        type: 'raster',
        tiles: [`${location.origin}/geo/earth/{z}/{x}/{y}.jpg`],
        tileSize: 256,
        minzoom: 0,
        maxzoom: 3,
        attribution: 'Earth imagery: NASA Visible Earth (Blue Marble)',
      },
      'pilot-relief': {
        type: 'image',
        url: '/geo/pilot-relief.jpg',
        coordinates: [
          [west, north],
          [east, north],
          [east, south],
          [west, south],
        ],
      },
      // Live elevation at native resolution. The baked relief above is only
      // 2048px across five degrees, so it smears once the camera gets close to
      // a habitation; this keeps ridges and valleys crisp all the way in. Same
      // dataset the baked relief was rendered from, so the two agree.
      terrain: {
        type: 'raster-dem',
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        encoding: 'terrarium',
        tileSize: 256,
        minzoom: 0,
        maxzoom: 13,
        attribution: 'Elevation: Mapzen / AWS Terrain Tiles',
      },
      ...(remote?.sources ?? {}),
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#16241f' } },
      {
        id: 'earth',
        type: 'raster',
        source: 'earth',
        paint: {
          // hands over to the terrain + vector detail as the camera descends
          'raster-opacity': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 8.5, 0],
          'raster-fade-duration': 300,
        },
      },
      {
        id: 'pilot-relief',
        type: 'raster',
        source: 'pilot-relief',
        paint: {
          // carries the colour of the land; hands its detail to the hillshade
          // once the camera is close enough for the stretch to show
          'raster-opacity': ['interpolate', ['linear'], ['zoom'], 4.5, 0, 7, 0.95, 11, 0.88, 13, 0.82],
          'raster-saturation': -0.1,
        },
      },
      {
        id: 'hillshade',
        type: 'hillshade',
        source: 'terrain',
        // Exaggeration is already 0 below z6, but without a minzoom the source
        // still fetched, decoded and shaded DEM tiles through the globe and
        // India phases to draw nothing. Gating the layer keeps all of that
        // work out of the flight and starts it only on final approach.
        minzoom: 7,
        paint: {
          // a shading pass, not a colour pass: the highlight stays a muted
          // sage so ridges gain form without bleaching to grey
          'hillshade-shadow-color': '#03100d',
          'hillshade-highlight-color': '#8fae9d',
          'hillshade-accent-color': '#16302a',
          'hillshade-illumination-direction': 318,
          'hillshade-exaggeration': ['interpolate', ['linear'], ['zoom'], 6, 0, 8, 0.34, 12, 0.5],
        },
      },
      ...((remote?.layers ?? []).filter(keepRemoteLayer).map(dampRemoteLayer) as LayerSpecification[]),
    ],
  }

  return style
}
