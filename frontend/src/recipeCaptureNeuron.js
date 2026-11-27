// Packed features of Japanese Neuron printings. A CID identifies a card, an artwork ID
// identifies the pictured illustration. Local card/variant IDs are resolved by the API.
export function readNeuronIndex(buffer) {
  const view = new DataView(buffer)
  if (buffer.byteLength < 8 || view.getUint32(0) !== 0x594e5231) throw new Error('그림 지문을 읽을 수 없습니다.')
  const count = view.getUint32(4, true)
  if (count > 60000 || buffer.byteLength !== 8 + count * 59) throw new Error('그림 지문의 길이가 올바르지 않습니다.')
  const entries = []
  for (let i = 0; i < count; i++) {
    const offset = 8 + i * 59
    const descriptor = new Uint8Array(108)
    for (let j = 0; j < 54; j++) {
      const pair = view.getUint8(offset + 5 + j)
      descriptor[2*j] = (pair & 240) + 8
      descriptor[2*j + 1] = (pair & 15) * 16 + 8
    }
    entries.push({ card:{ konamiId:String(view.getUint32(offset,true)), neuronArtwork:view.getUint8(offset+4) }, descriptor })
  }
  return entries
}
