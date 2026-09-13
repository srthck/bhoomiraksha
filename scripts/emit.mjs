import fs from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire('C:/Users/Sarthak/Desktop/bhoomi_raksha/package.json')
const { simplify } = require('@turf/simplify')
const { union } = require('@turf/union')
const { featureCollection, multiPolygon } = require('@turf/helpers')

const Z = 6, TS = 256, WORLD = TS * (1 << Z)
const GX0 = 43 * TS, GY0 = 24 * TS
const CX0 = 140, CY0 = 210, S = 1400 / 1640
const VW = 1400, VH = 1468

const px = (lon) => ((lon + 180) / 360 * WORLD - GX0 - CX0) * S
const py = (lat) => {
  const r = lat * Math.PI / 180
  return ((0.5 - Math.log(Math.tan(Math.PI / 4 + r / 2)) / (2 * Math.PI)) * WORLD - GY0 - CY0) * S
}
const area = (r) => { let a = 0; for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += r[j][0] * r[i][1] - r[i][0] * r[j][1]; return Math.abs(a / 2) }
const ring = (r) => 'M' + r.map(([lo, la]) => `${px(lo).toFixed(1)} ${py(la).toFixed(1)}`).join('L') + 'Z'

const src = JSON.parse(fs.readFileSync('india_state.geojson', 'utf8'))
// display geometry is coarser than the raster mask: sub-pixel detail costs bytes, not clarity
const MIN = 0.02
const states = []
for (const f of src.features) {
  const s = simplify(f, { tolerance: 0.03, highQuality: true, mutate: false })
  const polys = (s.geometry.type === 'Polygon' ? [s.geometry.coordinates] : s.geometry.coordinates)
    .filter((p) => area(p[0]) >= MIN)
  if (polys.length) states.push({ name: f.properties.NAME_1, polys })
}

let acc = null
for (const s of states) {
  const g = multiPolygon(s.polys)
  if (!acc) { acc = g; continue }
  try { acc = union(featureCollection([acc, g])) ?? acc } catch { /* topology failure: keep prior union */ }
}
const outRings = (acc.geometry.type === 'Polygon' ? [acc.geometry.coordinates] : acc.geometry.coordinates)
  .filter((p) => area(p[0]) >= MIN)

const statePaths = states.map((s) => ({ name: s.name, d: s.polys.map((p) => ring(p[0])).join('') }))
const outline = outRings.map((p) => ring(p[0])).join('')

// hazard anchors are real places, positioned from their coordinates and expressed
// as percentages so the CSS layer stays resolution independent
const hazards = [
  { id: 'himalayan-slope', label: 'Himalayan slope belt', kind: 'landslide', level: 'critical', lon: 77.4, lat: 31.9 },
  { id: 'brahmaputra', label: 'Brahmaputra basin', kind: 'flood', level: 'critical', lon: 92.4, lat: 26.5 },
  { id: 'gangetic', label: 'Gangetic plain', kind: 'flood', level: 'high', lon: 85.4, lat: 25.7 },
  { id: 'thar', label: 'Arid west', kind: 'heat', level: 'high', lon: 72.2, lat: 26.6 },
  { id: 'east-coast', label: 'East coast', kind: 'cyclone', level: 'critical', lon: 85.6, lat: 19.4 },
  { id: 'kutch', label: 'Kutch', kind: 'heat', level: 'monitor', lon: 70.2, lat: 23.4 },
  { id: 'western-ghats', label: 'Western Ghats', kind: 'landslide', level: 'high', lon: 76.4, lat: 11.2 },
  { id: 'konkan', label: 'Konkan coast', kind: 'cyclone', level: 'monitor', lon: 73.1, lat: 17.4 },
]
const anchors = hazards.map((h) => ({
  id: h.id, label: h.label, kind: h.kind, level: h.level,
  x: +(px(h.lon) / VW * 100).toFixed(2), y: +(py(h.lat) / VH * 100).toFixed(2),
}))

const ts = `// Generated from GADM India state boundaries, projected to the terrain raster in
// public/geo (Web Mercator, zoom 6). Regenerate with scripts/build-india-assets.
export const INDIA_VIEWBOX = { width: ${VW}, height: ${VH} } as const

export type HazardKind = 'landslide' | 'flood' | 'heat' | 'cyclone'
export type HazardLevel = 'critical' | 'high' | 'monitor'
export type HazardAnchor = { id: string; label: string; kind: HazardKind; level: HazardLevel; x: number; y: number }

/** Illustrative hazard belts for the landing visual. Not a live national assessment. */
export const HAZARD_ANCHORS: HazardAnchor[] = ${JSON.stringify(anchors, null, 2)}

export const INDIA_OUTLINE = '${outline}'

export const INDIA_STATES: { name: string; d: string }[] = [
${statePaths.map((s) => `  { name: ${JSON.stringify(s.name)}, d: '${s.d}' },`).join('\n')}
]
`
fs.writeFileSync('indiaGeometry.ts', ts)
console.log('states', statePaths.length, 'outline rings', outRings.length, 'bytes', ts.length)
console.log(anchors.map((a) => `${a.id} ${a.x}% ${a.y}%`).join('\n'))
