// Neuron's portrait recipe uses ten columns. Estimate the actual pitch, margins and
// row bounds from the pixels, so scaled exports and uneven final rows remain usable.
const COLUMNS = 10
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n))

function quantile(values, fraction) {
  const sorted = Array.from(values).sort((a, b) => a - b)
  return sorted[Math.floor((sorted.length - 1) * fraction)]
}

function pixel(image, x, y) {
  return 4 * (clamp(Math.round(y), 0, image.height - 1) * image.width +
    clamp(Math.round(x), 0, image.width - 1))
}

function difference(data, a, b) {
  return Math.max(Math.abs(data[a] - data[b]), Math.abs(data[a + 1] - data[b + 1]),
    Math.abs(data[a + 2] - data[b + 2]))
}

function columnGrid(image) {
  const { width, height, data } = image
  const vertical = new Float32Array(width)
  const horizontal = new Float32Array(width)
  const skip = Math.max(1, Math.floor(height / 600))
  for (let y = 1; y < height; y += skip) {
    for (let x = 1; x < width; x++) {
      const i = 4 * (y * width + x)
      vertical[x] += Math.min(difference(data, i, i - width * 4), 100)
      horizontal[x] += Math.min(difference(data, i, i - 4), 100)
    }
  }
  // Blank gutters have little vertical texture, bounded by the long left/right card edges.
  const cost = (profile, x) => profile[clamp(Math.round(x), 0, width - 1)]
  let best = null
  const minPitch = width * .72 / COLUMNS
  const maxPitch = width / (COLUMNS - .15)
  for (let pitch = minPitch; pitch <= maxPitch; pitch += .25) {
    const spare = width - pitch * COLUMNS
    const low = Math.max(-pitch * .12, spare / 2 - width * .04)
    const high = Math.min(width * .2, spare / 2 + width * .04)
    for (let left = low; left <= high; left += 1) {
      let score = 0
      for (let col = 1; col < COLUMNS; col++) {
        const seam = left + pitch * col
        const mid = seam + pitch * .43
        const gutter = cost(vertical, seam)
        const flank = Math.max(cost(horizontal, seam - pitch * .04),
          cost(horizontal, seam + pitch * .04), cost(horizontal, seam))
        score += .85 * (cost(vertical, mid) - gutter) + flank * .60
      }
      if (!best || score > best.score) best = { left, pitch, score }
    }
  }
  const seamRatios = []
  for (let col = 1; col < COLUMNS; col++) {
    const seam = best.left + col * best.pitch
    const middle = cost(vertical, seam + best.pitch * .43)
    if (middle > 0) seamRatios.push(cost(vertical, seam) / middle)
  }
  return seamRatios.length >= 3 && quantile(seamRatios,.5) < .78 ? best : null
}

function occupancy(image, grid) {
  const { width, height, data } = image
  const { left, pitch } = grid
  const active = new Uint8Array(height * COLUMNS)
  const edges = new Float32Array(height)
  const isRow = new Uint8Array(height)
  const gutter = []
  for (let j = 0; j <= COLUMNS; j++) {
    const x = left + j * pitch
    if (x >= 0 && x < width) gutter.push(Math.round(x))
  }
  for (let y = 0; y < height; y++) {
    // The backgrounds in both light and dark exports are locally uniform in the gutters.
    const colors = gutter.map(x => 4 * (y * width + x))
    const bg = [0, 1, 2].map(c => quantile(colors.map(i => data[i + c]), .5))
    let count = 0
    for (let col = 0; col < COLUMNS; col++) {
      let ink = 0, variation = 0, prev = -1
      for (let s = 0; s < 15; s++) {
        const x = left + pitch * (col + .065 + s * .062)
        const at = pixel(image, x, y)
        if (Math.max(...bg.map((v, c) => Math.abs(data[at+c] - v))) > 29) ink++
        if (prev !== -1) variation += Math.min(difference(data, at, prev), 90)
        if (y) edges[y] += Math.min(difference(data, at, at - 4 * width), 100)
        prev = at
      }
      if (ink >= 8 || variation >= 260 && ink >= 4) {
        active[y * COLUMNS + col] = 1
        count++
      }
    }
    isRow[y] = count >= 3 || active[y * COLUMNS] && count >= 1 ? 1 : 0
  }
  return { active, edges, isRow }
}

function bands(bits, gap) {
  const rows = []
  let start = -1, end = -1
  for (let y = 0; y < bits.length; y++) {
    if (bits[y]) {
      if (start < 0) start = y
      end = y + 1
    } else if (start >= 0 && y - end >= gap) {
      rows.push([start, end])
      start = -1
    }
  }
  if (start >= 0) rows.push([start, end])
  return rows
}

function partition(start, end, pitch, edges) {
  const expected = pitch * 1.41
  const n = Math.max(1, Math.round((end - start) / expected))
  const actual = (end - start) / n
  if (actual < pitch * 1.07 || actual > pitch * 1.65) return []
  const cuts = [start]
  for (let i = 1; i < n; i++) {
    const mean = start + i * actual
    const wiggle = Math.max(2, Math.round(.095 * pitch))
    let cut = Math.round(mean), best = -Infinity
    for (let y = Math.round(mean) - wiggle; y <= mean + wiggle; y++) {
      const score = edges[y] * (1 - .4 * Math.abs(y - mean) / wiggle)
      if (score > best) { best = score; cut = y }
    }
    cuts.push(cut)
  }
  cuts.push(end)
  return cuts.slice(0, -1).map((y, i) => [y, cuts[i + 1]])
}

function alignRows(rows, pitch, edges) {
  // White rules text can disappear against the background. Recover the outer card
  // border and common row pitch from edge peaks shared by multiple rows and columns.
  const first = rows[0].top
  let best = {score:-Infinity}
  for (let step = pitch*1.32; step <= pitch*1.52; step += .30) {
    for (let top = Math.round(first-pitch*.22); top <= first+pitch*.14; top++) {
      if (top < 0) continue
      const height = Math.round(step*.975)
      let strength = 0
      for (let j = 0; j < rows.length; j++) {
        const y = Math.round(top+j*step)
        const end = y+height
        const edge = (edges[y] || 0) + Math.max(edges[end-1] || 0, edges[end] || 0, edges[end+1] || 0)
        const displacement = Math.abs(y-rows[j].top)/pitch
        strength += edge / (1+displacement)
      }
      if (strength > best.score) best = { top, step, height, score:strength }
    }
  }
  return rows.map((row,i) => {
    const y = Math.round(best.top+i*best.step)
    const h = Math.min(best.height, edges.length-y)
    return row.cells.map(cell => ({ ...cell, y, h }))
  })
}

export function detectRecipeGrid(image) {
  if (image.width < 200 || image.height < 60) return []
  const grid = columnGrid(image)
  if (!grid) return []
  const { pitch, left } = grid
  const { active, edges, isRow } = occupancy(image, grid)
  const ranges = bands(isRow, Math.max(1, Math.round(.035 * pitch)))
  const rows = []
  for (const [start, end] of ranges) {
    for (const [top, bottom] of partition(start, end, pitch, edges)) {
      const cells = []
      for (let col = 0; col < COLUMNS; col++) {
        let hits = 0, samples = 0
        for (let y = top; y < bottom; y++) { hits += active[y * COLUMNS + col]; samples++ }
        if (hits < samples * .47) break
        const h = bottom - top
        const w = pitch * .97
        cells.push({ x: left + pitch * (col + .5) - w / 2, y: top, w, h })
      }
      if (cells.length) rows.push({ top, bottom, cells })
    }
  }
  if (!rows.length || !rows.some(r => r.cells.length >= 4)) return []
  const sections = ['MAIN', 'EXTRA', 'SIDE']
  const boundaries = []
  for (let i = 1; i < rows.length; i++) {
    const gap = rows[i].top - rows[i - 1].bottom
    if (gap >= pitch * .20) boundaries.push({ i, gap })
  }
  // One section heading can contain several text scan lines. Only the two widest
  // significant breaks separate the three physical sections of a Neuron export.
  const cuts = new Set(boundaries.sort((a, b) => b.gap - a.gap).slice(0, 2).map(b => b.i))
  const starts = [0, ...[...cuts].sort((a,b) => a-b), rows.length]
  return starts.slice(0,-1).flatMap((start,i) =>
    alignRows(rows.slice(start,starts[i+1]),pitch,edges).flat().map(rect => ({ ...rect, section:sections[i] })))
}

const BLOCKS = 6
export function describeArt(image, tile) {
  const sample = new Uint8Array(BLOCKS * BLOCKS * 3)
  const { data } = image
  let index = 0
  // Ignore lettering and the effect box. Neuron omits much printed text and crop
  // edges vary slightly between an electronic deck sheet and a photographed card.
  for (let by = 0; by < BLOCKS; by++) {
    for (let bx = 0; bx < BLOCKS; bx++) {
      const rgb = [0, 0, 0]
      for (let j = 0; j < 4; j++) for (let i = 0; i < 4; i++) {
        const x = tile.x + tile.w * (.105 + .79 * (bx + (i + .5) / 4) / BLOCKS)
        const y = tile.y + tile.h * (.185 + .535 * (by + (j + .5) / 4) / BLOCKS)
        const at = pixel(image, x, y)
        for (let c = 0; c < 3; c++) rgb[c] += data[at + c]
      }
      for (const value of rgb) sample[index++] = Math.round(value / 16)
    }
  }
  return sample
}

export function artDistance(a, b) {
  let sum = 0, worst = 0
  for (let i = 0; i < a.length; i += 3) {
    const red = Math.abs(a[i] - b[i])
    const green = Math.abs(a[i + 1] - b[i + 1])
    const blue = Math.abs(a[i + 2] - b[i + 2])
    const d = (red + 1.5 * green + blue) / 3.5
    // A small overprinted SAMPLE mark or a foil flash affects only part of the art.
    sum += Math.min(75, d)
    worst = Math.max(worst, Math.min(75, d))
  }
  return (sum - worst) / (BLOCKS * BLOCKS - 1)
}

export function rankArt(descriptor, index, limit = 5) {
  const best = []
  for (const item of index) {
    const distance = artDistance(descriptor, item.descriptor)
    if (best.length === limit && distance >= best[best.length - 1].distance) continue
    best.push({ item, distance })
    best.sort((a, b) => a.distance - b.distance)
    if (best.length > limit) best.pop()
  }
  const first = best[0]?.distance ?? Infinity
  const margin = (best[1]?.distance ?? Infinity) - first
  const confidence = first > 40 ? 'unmatched' : first < 22 && margin >= 4 ? 'high' : 'review'
  return {
    confidence,
    candidates: best.map(({ item, distance }) => ({
      ...item.card, score: Math.round(Math.max(0, 1 - distance / 100) * 1000) / 1000,
    })),
  }
}
