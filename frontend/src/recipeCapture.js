import { checkCropSource } from './cropSource.js'
import { artDistance, describeArt } from './recipeCaptureVision.js'

const SHEET_PATH = /^\/media\/sheets\/[a-f0-9]{64}\.webp$/
const MAX_REFERENCES = 60000
const CACHE_NAME = 'tcg-recipe-signatures-v1'
const ENTRIES = 'sheets'

function checkCancelled(signal) {
  if (signal?.aborted) throw new DOMException('취소했습니다.', 'AbortError')
}

function canvas(width, height) {
  const surface = document.createElement('canvas')
  surface.width = width
  surface.height = height
  return surface
}

function processPixels(worker, message, transfers, signal) {
  checkCancelled(signal)
  return new Promise((resolve, reject) => {
    function finish(callback, value) {
      signal?.removeEventListener('abort', cancel)
      worker.onmessage = worker.onerror = null
      callback(value)
    }
    function cancel() { finish(reject, new DOMException('취소했습니다.', 'AbortError')) }
    signal?.addEventListener('abort', cancel, { once: true })
    worker.onerror = () => finish(reject, new Error('캡처의 그림을 분석하는 중 오류가 발생했습니다.'))
    worker.onmessage = ({ data }) => data.error ? finish(reject, new Error(data.error)) : finish(resolve, data)
    worker.postMessage(message, transfers)
  })
}

async function sheetGroups(signal) {
  const groups = new Map()
  let after = 0
  let total = 0
  for (;;) {
    const response = await fetch('/api/v1/cards/capture-index?after=' + after,
      { signal, cache: 'no-store', credentials: 'omit' })
    if (!response.ok) throw new Error('도감의 일러스트 목록을 불러올 수 없습니다.')
    const page = await response.json()
    if (!Array.isArray(page.items)) throw new Error('도감에서 올바른 목록을 받지 못했습니다.')
    for (const row of page.items) {
      const tile = row.image
      if (!tile || !SHEET_PATH.test(tile.url) || !Number.isInteger(tile.col) || tile.col < 0 || tile.col > 3 ||
          !Number.isInteger(tile.row) || tile.row < 0 || tile.row > 2) continue
      if (!groups.has(tile.url)) groups.set(tile.url, [])
      groups.get(tile.url).push(row)
      total++
    }
    if (total > MAX_REFERENCES) throw new Error('도감의 이미지가 기기 처리 한도를 초과했습니다.')
    if (page.next == null) break
    if (!Number.isSafeInteger(page.next) || page.next <= after) throw new Error('도감 목록을 계속 읽을 수 없습니다.')
    after = page.next
  }
  return groups
}

// The cache holds 108 numerical features per tile, keyed by the immutable sheet hash.
// It contains no uploaded screenshot or thumbnails. Repacked/replaced art gets a new key.
function openCache() {
  return new Promise(resolve => {
    try {
      const req = indexedDB.open(CACHE_NAME, 1)
      req.onupgradeneeded = () => req.result.createObjectStore(ENTRIES)
      req.onsuccess = () => resolve(req.result)
      req.onerror = req.onblocked = () => resolve(null)
    } catch { resolve(null) }
  })
}

function cacheOp(db, write, act) {
  if (!db) return Promise.resolve(null)
  return new Promise(resolve => {
    try {
      const tx = db.transaction(ENTRIES, write ? 'readwrite' : 'readonly')
      const req = act(tx.objectStore(ENTRIES))
      tx.oncomplete = () => resolve(req.result ?? null)
      tx.onerror = tx.onabort = () => resolve(null)
    } catch { resolve(null) }
  })
}

async function referenceIndex(groups, onProgress, signal) {
  const db = await openCache()
  const refs = []
  let completed = 0, missingSheets = 0
  try {
    // One bounded sheet at a time, including on a mobile device with limited memory.
    const surface = canvas(4 * 64, 3 * 94)
    const ctx = surface.getContext('2d', { willReadFrequently: true })
    for (const [url, rows] of groups) {
      checkCancelled(signal)
      let signatures = await cacheOp(db, false, store => store.get(url))
      if (!(signatures instanceof Array) || signatures.length !== 12) {
        const response = await fetch(url, { signal, credentials: 'omit' })
        if (response.status === 404 || response.status === 410) {
          missingSheets++
          onProgress({ stage:'index', done:++completed, total:groups.size })
          continue
        }
        if (!response.ok) throw new Error('도감 이미지를 받을 수 없습니다. 연결을 확인해 주세요.')
        const bitmap = await createImageBitmap(await response.blob())
        try { ctx.drawImage(bitmap, 0, 0, surface.width, surface.height) }
        finally { bitmap.close() }
        const image = ctx.getImageData(0, 0, surface.width, surface.height)
        signatures = Array.from({ length:12 }, (_, index) =>
          describeArt(image, { x:(index % 4) * 64, y:Math.floor(index / 4) * 94, w:64, h:94 }))
        await cacheOp(db, true, store => store.put(signatures, url))
      }
      for (const card of rows) refs.push({ card, descriptor:signatures[card.image.row * 4 + card.image.col] })
      onProgress({ stage:'index', done:++completed, total:groups.size })
    }
    if (db) {
      const oldKeys = await cacheOp(db, false, store => store.getAllKeys())
      for (const key of oldKeys || []) if (!groups.has(key)) await cacheOp(db, true, store => store.delete(key))
    }
  } finally { db?.close() }
  return { refs, missingSheets }
}

export function captureFileTitle(filename) {
  const name = String(filename || '').split(/[\\/]/).pop().replace(/\.(png|jpe?g|webp)$/i, '').trim()
  if (!name || name.length > 100 || /^(?:screen[ _-]?(?:shot|capture)|image|img|capture|download|file|photo|screenshot|스크린[ _-]?[샷숏]|화면[ _-]?캡처|캡처|다운로드|スクリーンショット|画像)(?:[\d\W_]|$)/iu.test(name) ||
      !/\p{L}/u.test(name) || /^[\da-f-]{16,}$/i.test(name)) return ''
  return name
}

async function suggestedTitle(surface, slots, filename) {
  const fallback = captureFileTitle(filename)
  // Native OCR is optional. A partial capture beginning at the first row has no header.
  const top = Math.floor(slots[0]?.y || 0)
  if (top > 20 && typeof globalThis.TextDetector === 'function') {
    try {
      const header = canvas(surface.width, top)
      header.getContext('2d').drawImage(surface, 0, 0, surface.width, top, 0, 0, header.width, header.height)
      const lines = await new TextDetector().detect(header)
      const ignored = /メインデッキ|エクストラデッキ|サイドデッキ|デッキ(?:レシピ|コード)|main deck|extra deck|side deck|deck recipe|메인 덱|엑스트라 덱|사이드 덱|덱 레시피|카드 게임|ニューロン|遊戯王|yu-gi-oh|konami|몬스터|monster|[0-9]+[枚장]/i
      const titles = lines.filter(line => {
        const name = line.rawValue?.trim() || ''
        return name.length > 1 && name.length <= 100 && /\p{L}/u.test(name) &&
          !ignored.test(name) && line.boundingBox?.x < surface.width * .6
      }).sort((a,b) => b.boundingBox.height - a.boundingBox.height)
      if (titles.length && (titles.length === 1 || titles[0].boundingBox.height > titles[1].boundingBox.height * 1.2)) {
        return { suggestedTitle:titles[0].rawValue.trim(), titleSource:'image' }
      }
    } catch { /* Offer the original editable filename when the native OCR service is unavailable. */ }
  }
  return { suggestedTitle:fallback, titleSource:fallback ? 'filename' : null }
}

function groupSlots(slots) {
  const rows = []
  for (const slot of slots) {
    const match = rows.find(row => row.section === slot.section && artDistance(row.descriptor,slot.descriptor) < 5)
    if (match) match.quantity++
    else rows.push({ ...slot, quantity:1 })
  }
  return rows
}

async function publishedIdentities(matches, signal) {
  const identities = new Map()
  const ids = [...new Set(matches.flatMap(match => match.neuron.map(hit => hit.konamiId)))]
  for (let i = 0; i < ids.length; i += 100) {
    const query = new URLSearchParams({ ids:ids.slice(i, i+100).join(',') })
    const response = await fetch('/api/v1/cards/capture-identities?' + query,
      { signal, credentials:'omit', cache:'no-store' })
    if (!response.ok) throw new Error('인식한 그림의 공개 카드 정보를 읽을 수 없습니다.')
    for (const item of await response.json()) identities.set(item.konamiId, item)
  }
  return identities
}

export function resolveMatch(match, refs, identities) {
  const local = new Map(match.local.map(({position,score}) => [position,{...refs[position].card,score}]))
  const candidates = [...local.values()]
  for (const hit of match.neuron) {
    const printing = identities.get(hit.konamiId)
    const imageUrl = printing?.artworks?.[hit.neuronArtwork]
    if (!imageUrl) continue
    const { artworks, ...card } = printing
    const tile = local.get(hit.localPosition)
    if (tile && tile.konamiId === hit.konamiId && tile.neuronArtwork == null) {
      tile.neuronArtwork = hit.neuronArtwork
      tile.score = Math.max(hit.score, tile.score)
    } else {
      candidates.push({ ...card, variantId:null, artworkIndex:hit.neuronArtwork, image:null,
        imageUrl, neuronArtwork:hit.neuronArtwork, score:hit.score })
    }
  }
  candidates.sort((a,b) => b.score-a.score)
  const best = candidates[0]?.score ?? 0
  const runner = candidates[1]?.score ?? 0
  const unavailable = match.neuron.find(hit => !identities.get(hit.konamiId)?.artworks?.[hit.neuronArtwork])?.score ?? 0
  const credible = best >= .78 && best-runner >= .04 && best-unavailable >= .035
  return {confidence:best < .60 ? 'unmatched' : credible ? 'high' : 'review', candidates:candidates.slice(0,5)}
}

export function mergeConfirmedRows(rows) {
  const seen = new Map()
  const merged = []
  for (const row of rows) {
    const best = row.candidates[0]
    const key = row.confidence !== 'high' ? null : best?.konamiId && best.neuronArtwork != null
      ? row.section + '/n/' + best.konamiId + '/' + best.neuronArtwork
      : best?.variantId != null ? row.section + '/v/' + best.variantId : null
    const previous = key && seen.get(key)
    if (previous) previous.quantity += row.quantity
    else {
      const copy = {...row}
      merged.push(copy)
      if (key) seen.set(key,copy)
    }
  }
  return merged
}

function thumbnail(surface, rect, dest) {
  const ctx = dest.getContext('2d')
  ctx.clearRect(0, 0, dest.width, dest.height)
  ctx.drawImage(surface, rect.x, rect.y, rect.w, rect.h, 0, 0, dest.width, dest.height)
  return dest.toDataURL('image/jpeg', .82)
}

export async function recognizeRecipeCapture(file, { game = 'YUGIOH', signal, onProgress = () => {} } = {}) {
  if (game !== 'YUGIOH') throw new Error('뉴런 레시피 인식은 유희왕 덱에서 사용할 수 있습니다.')
  checkCancelled(signal)
  onProgress({ stage:'decode', done:0, total:1 })
  await checkCropSource(file)
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, 900 / bitmap.width, 3500 / bitmap.height)
  const surface = canvas(Math.max(1, Math.round(bitmap.width * scale)), Math.max(1, Math.round(bitmap.height * scale)))
  const ctx = surface.getContext('2d', { willReadFrequently:true })
  try { ctx.drawImage(bitmap, 0, 0, surface.width, surface.height) }
  finally { bitmap.close() }
  const worker = new Worker(new URL('./recipeCaptureWorker.js', import.meta.url), { type:'module' })
  try {
    onProgress({ stage:'detect', done:0, total:1 })
    const image = ctx.getImageData(0, 0, surface.width, surface.height)
    const detected = await processPixels(worker, { kind:'detect', image }, [image.data.buffer], signal)
    if (!detected.slots.length || detected.slots.length > 180) {
      throw new Error('카드 배열을 찾을 수 없습니다. 메인·엑스트라·사이드가 보이는 전체 레시피 이미지를 선택해 주세요.')
    }
    const slots = groupSlots(detected.slots)
    const title = await suggestedTitle(surface, slots, file.name)
    const groups = await sheetGroups(signal)
    onProgress({ stage:'index', done:0, total:groups.size })
    const { refs, missingSheets } = await referenceIndex(groups, onProgress, signal)
    onProgress({ stage:'match', done:0, total:slots.length })
    const ranked = await processPixels(worker, {
      kind:'rank', slots:slots.map(({ descriptor }) => ({ descriptor })),
      index:refs.map(r => ({descriptor:r.descriptor,konamiId:r.card.konamiId})),
    }, [], signal)
    const identities = await publishedIdentities(ranked.matches, signal)
    const thumb = canvas(64, 92)
    const counts = { MAIN:0, EXTRA:0, SIDE:0 }
    const rows = slots.map((slot, i) => {
      counts[slot.section] += slot.quantity
      const result = resolveMatch(ranked.matches[i], refs, identities)
      return {
        section:slot.section, quantity:slot.quantity, thumbnail:thumbnail(surface, slot, thumb),
        ...result,
      }
    })
    onProgress({ stage:'match', done:slots.length, total:slots.length })
    return { rows:mergeConfirmedRows(rows), counts, ...title, referenceCount:refs.length+ranked.neuronCount, missingSheets }
  } finally {
    worker.terminate()
    surface.width = surface.height = 1
  }
}
