// Chosen champions, leaders, runes and sideboard cards start outside the draw pile.
export function drawableEntries(entries) {
  return entries.filter(entry => entry.section === 'MAIN' && Number.isInteger(entry.quantity) && entry.quantity > 0)
}

export const openingSizes = {YUGIOH:5, POKEMON:7, ONEPIECE:5, WEISS:5, NIVEL:5, RIFTBOUND:4}

export function curve(entries) {
  const bins = new Map()
  let unknown = 0
  for (const {curveValue, quantity} of entries) {
    if (Number.isInteger(curveValue) && curveValue >= 0) bins.set(curveValue, (bins.get(curveValue) || 0) + quantity)
    else unknown += quantity
  }
  return {bins:[...bins].sort(([a],[b])=>a-b), unknown}
}

// Sample by remaining quantity without allocating one object per physical copy.
export function openingHand(entries, size, random = Math.random) {
  if (!Number.isInteger(size) || size < 1 || size > 10) return []
  const counts = entries.map(entry => entry.quantity)
  let remaining = counts.reduce((sum,quantity)=>sum+quantity,0)
  const hand = []
  while (hand.length < size && remaining > 0) {
    let index = 0
    let offset = Math.floor(random()*remaining)
    while (offset >= counts[index]) {
      offset -= counts[index]
      index++
    }
    hand.push(entries[index])
    counts[index]--
    remaining--
  }
  return hand
}
