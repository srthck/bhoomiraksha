import fs from 'node:fs'
const NM = 'C:/Users/Sarthak/Desktop/bhoomi_raksha/node_modules'
const { createRequire } = await import('node:module'); const require = createRequire('C:/Users/Sarthak/Desktop/bhoomi_raksha/package.json'); const { simplify } = require('@turf/simplify')
const { union } = require('@turf/union')
const { featureCollection, multiPolygon } = require('@turf/helpers')

const Z = 6, TS = 256, WORLD = TS * (1 << Z)
const GX0 = 43 * TS, GY0 = 24 * TS, W = 7 * TS, H = 8 * TS
const px = (lon) => (lon + 180) / 360 * WORLD - GX0
const py = (lat) => {
  const r = lat * Math.PI / 180
  return (0.5 - Math.log(Math.tan(Math.PI / 4 + r / 2)) / (2 * Math.PI)) * WORLD - GY0
}
const ringArea = (ring) => { let a = 0; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1]; return Math.abs(a / 2) }

const src = JSON.parse(fs.readFileSync('india_state.geojson', 'utf8'))
const MIN_AREA = 0.0009 // deg^2, keeps Lakshadweep-scale islands, drops sliver noise

const states = []
for (const f of src.features) {
  const s = simplify(f, { tolerance: 0.006, highQuality: true, mutate: false })
  const polys = s.geometry.type === 'Polygon' ? [s.geometry.coordinates] : s.geometry.coordinates
  const kept = polys.filter((p) => ringArea(p[0]) >= MIN_AREA)
  if (!kept.length) continue
  states.push({ name: f.properties.NAME_1, polys: kept })
}
console.log('states:', states.length, 'rings:', states.reduce((n, s) => n + s.polys.length, 0))

const toPath = (polys) => polys.map((rings) => rings.map((ring) => {
  const pts = ring.map(([lo, la]) => `${px(lo).toFixed(1)},${py(la).toFixed(1)}`)
  return 'M' + pts.join('L') + 'Z'
}).join('')).join('')

// dissolve to a national outline
let acc = null
for (const s of states) {
  const g = multiPolygon(s.polys)
  if (!acc) { acc = g; continue }
  try { acc = union(featureCollection([acc, g])) ?? acc } catch { /* keep previous on topology failure */ }
}
const outPolys = acc.geometry.type === 'Polygon' ? [acc.geometry.coordinates] : acc.geometry.coordinates
const outlineKept = outPolys.filter((p) => ringArea(p[0]) >= MIN_AREA)
console.log('outline rings:', outlineKept.length)

const dStates = states.map((s) => ({ name: s.name, d: toPath(s.polys) }))
const dOutline = toPath(outlineKept)

fs.writeFileSync('mask.json', JSON.stringify({
  width: W, height: H,
  polys: states.flatMap((s) => s.polys).map((rings) => rings.map((r) => r.map(([lo, la]) => [px(lo), py(la)]))),
}))
fs.writeFileSync('geometry.json', JSON.stringify({ width: W, height: H, states: dStates, outline: dOutline }))
console.log('state path bytes:', dStates.reduce((n, s) => n + s.d.length, 0), 'outline bytes:', dOutline.length)
