// Keep pixel processing off the UI thread. No capture data leaves this worker/browser.
import { describeArt, detectRecipeGrid, rankArt } from './recipeCaptureVision.js'
import { readNeuronIndex } from './recipeCaptureNeuron.js'

self.onmessage = async ({ data }) => {
  try {
    if (data.kind === 'detect') {
      const slots = detectRecipeGrid(data.image)
      self.postMessage({ slots: slots.map(rect => ({ ...rect, descriptor: describeArt(data.image, rect) })) })
    } else if (data.kind === 'rank') {
      const local = data.index.map((descriptor, position) => ({ card: { position }, descriptor }))
      const response = await fetch(new URL('./recipeCaptureNeuron.bin', import.meta.url), { credentials:'omit' })
      if (!response.ok) throw new Error('뉴런 일러스트 지문을 불러올 수 없습니다.')
      const neuron = readNeuronIndex(await response.arrayBuffer())
      const matches = data.slots.map(slot => ({
        local: rankArt(slot.descriptor, local).candidates,
        neuron: rankArt(slot.descriptor, neuron).candidates,
      }))
      self.postMessage({ matches, neuronCount:neuron.length })
    }
  } catch (error) {
    self.postMessage({ error: error.message })
  }
}
