// Keep pixel processing off the UI thread. No capture data leaves this worker/browser.
import { describeArt, detectRecipeGrid, matchingLocalPosition, rankArt } from './recipeCaptureVision.js'
import { readNeuronIndex } from './recipeCaptureNeuron.js'

self.onmessage = async ({ data }) => {
  try {
    if (data.kind === 'detect') {
      const slots = detectRecipeGrid(data.image)
      self.postMessage({ slots: slots.map(rect => ({ ...rect, descriptor: describeArt(data.image, rect) })) })
    } else if (data.kind === 'rank') {
      const local = data.index.map(({descriptor,konamiId}, position) => ({card:{position,konamiId}, descriptor}))
      const response = await fetch(new URL('./recipeCaptureNeuron.bin', import.meta.url), { credentials:'omit' })
      if (!response.ok) throw new Error('뉴런 일러스트 지문을 불러올 수 없습니다.')
      const neuron = readNeuronIndex(await response.arrayBuffer())
      const editions = new Map()
      for (const ref of neuron) {
        if (!editions.has(ref.card.konamiId)) editions.set(ref.card.konamiId,[])
        editions.get(ref.card.konamiId).push(ref)
      }
      const matches = data.slots.map(slot => {
        const hits = rankArt(slot.descriptor,local).candidates
        const candidates = rankArt(slot.descriptor,neuron).candidates.map(hit => {
          const siblings = editions.get(hit.konamiId)
          const official = siblings.find(ref => ref.card.neuronArtwork === hit.neuronArtwork)
          return {...hit,localPosition:matchingLocalPosition(official,siblings,hits,local)}
        })
        return {local:hits,neuron:candidates}
      })
      self.postMessage({ matches, neuronCount:neuron.length })
    }
  } catch (error) {
    self.postMessage({ error: error.message })
  }
}
