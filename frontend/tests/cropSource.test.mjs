import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkCropSource } from '../src/cropSource.js'

function png(width, height) {
  const bytes = Buffer.alloc(24)
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(bytes)
  bytes.writeUInt32BE(13, 8)
  bytes.write('IHDR', 12)
  bytes.writeUInt32BE(width, 16)
  bytes.writeUInt32BE(height, 20)
  return bytes
}

function jpeg(width, height) {
  const bytes = Buffer.from([255,216, 255,224,0,4,0,0, 255,194,0,8,8,0,0,0,0,1])
  bytes.writeUInt16BE(height, 13)
  bytes.writeUInt16BE(width, 15)
  return bytes
}

function webp(type, width, height) {
  const bytes = Buffer.alloc(30)
  bytes.write('RIFF', 0)
  bytes.writeUInt32LE(22, 4)
  bytes.write('WEBP' + type, 8)
  if (type === 'VP8X') {
    bytes.writeUIntLE(width - 1, 24, 3)
    bytes.writeUIntLE(height - 1, 27, 3)
  } else if (type === 'VP8L') {
    bytes[20] = 0x2f
    bytes.writeUInt32LE((height - 1) * 16384 + width - 1, 21)
  } else {
    Buffer.from([0x9d, 1, 0x2a]).copy(bytes, 23)
    bytes.writeUInt16LE(width, 26)
    bytes.writeUInt16LE(height, 28)
  }
  return bytes
}

const headers = [
  ['png', png], ['jpeg', jpeg],
  ...['VP8 ', 'VP8L', 'VP8X'].map(type => ['webp', (w,h) => webp(type,w,h)]),
]

test('each supported encoding accepts 12 MP and rejects larger dimensions before decoding', async () => {
  for (const [extension, encode] of headers) {
    await checkCropSource(new File([encode(4000, 3000)], 'camera.' + extension))
    await assert.rejects(checkCropSource(new File([encode(4001, 3000)], 'large.' + extension)), /픽셀/)
  }
})

test('requires matching extension and signature, complete dimensions and a still WebP', async () => {
  await assert.rejects(checkCropSource(new File([png(40, 80)], 'wrong.jpg')), /형식/)
  await assert.rejects(checkCropSource(new File([jpeg(40, 80).subarray(0,13)], 'cut.jpg')), /형식/)
  await assert.rejects(checkCropSource(new File([png(0, 80)], 'zero.png')), /형식/)
  const animated = webp('VP8X', 40, 80)
  animated[20] = 2
  await assert.rejects(checkCropSource(new File([animated], 'animated.webp')), /정지 이미지/)
})

test('rejects oversized files before allocating a read buffer', async () => {
  await assert.rejects(checkCropSource({size:8 * 1024 * 1024 + 1}), /8 MiB/)
})
