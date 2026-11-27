import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { detectRecipeGrid, describeArt, matchingLocalPosition, rankArt } from '../src/recipeCaptureVision.js'
import { readNeuronIndex } from '../src/recipeCaptureNeuron.js'
import { captureFileTitle, mergeConfirmedRows, resolveMatch } from '../src/recipeCapture.js'

function recipe(counts, pitch = 34) {
  const width = pitch * 10 + 10
  const height = 32 + counts.reduce((total,copies) => total + Math.ceil(copies/10)*pitch*1.44+28,0)
  const image = { width, height:Math.ceil(height), data:new Uint8ClampedArray(width*Math.ceil(height)*4).fill(238) }
  let y = 22
  for (const count of counts) {
    for (let i = 0; i < count; i++) {
      const left = 5 + i%10*pitch
      const top = y + Math.round(Math.floor(i/10)*pitch*1.44)
      for (let dy=0; dy<Math.floor(pitch*1.4); dy++) for (let dx=0; dx<pitch-1; dx++) {
        const at = ((top+dy)*width+left+dx)*4
        const edge = dx===0 || dy===0 || dx===pitch-2 || dy===Math.floor(pitch*1.4)-1
        image.data[at] = edge ? 25 : 50+((i*3 + dx*4+dy)%166)
        image.data[at+1] = edge ? 25 : 20+((i*7+dx+5*dy)%189)
        image.data[at+2] = edge ? 25 : 40+((i*13+dx+dy)%159)
      }
    }
    y += Math.ceil(Math.ceil(count/10)*pitch*1.44)+28
  }
  return image
}
test('ten-column light grids preserve incomplete rows and section boundaries', () => {
  const slots = detectRecipeGrid(recipe([43,12,7]))
  assert.deepEqual(['MAIN','EXTRA','SIDE'].map(s=>slots.filter(t=>t.section===s).length),[43,12,7])
  assert.ok(slots.every(r=>Number.isFinite(r.x+r.y+r.w+r.h)))
})
test('white documents and non-grid textures cannot become guessed decks', () => {
  const image = {width:350,height:600,data:new Uint8ClampedArray(350*600*4)}
  assert.deepEqual(detectRecipeGrid(image),[])
  let value = 17
  for (let i=0; i<image.data.length; i++) {
    value = (Math.imul(1664525,value)+1013904223)>>>0
    image.data[i] = value>>>24
  }
  assert.deepEqual(detectRecipeGrid(image),[])
})
test('real reference index has supported card and alternative artwork identities', async () => {
  const bytes = await readFile(new URL('../src/recipeCaptureNeuron.bin',import.meta.url))
  const entries = readNeuronIndex(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset+bytes.byteLength))
  assert.ok(entries.length >= 15000)
  const magician = entries.filter(item=>item.card.konamiId==='4041')
  assert.ok(magician.length > 2)
  const found = rankArt(magician[1].descriptor,entries)
  assert.equal(found.candidates[0].konamiId,'4041')
  assert.equal(found.candidates[0].neuronArtwork,magician[1].card.neuronArtwork)
  assert.throws(()=>readNeuronIndex(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+14)))
})
test('same-CID editions remain distinct and a nonexistent official painting never gets a local variant id', () => {
  const refs = [{card:{cardId:18,variantId:123,artworkIndex:2,konamiId:'4041'}}]
  const map = new Map([['4041',{cardId:18,konamiId:'4041',artworks:{1:'first.png',3:'third.png'}}]])
  const both = resolveMatch({local:[{position:0,score:.91}],neuron:[
    {konamiId:'4041',neuronArtwork:3,score:.92,localPosition:0},{konamiId:'4041',neuronArtwork:1,score:.81}]},refs,map)
  assert.equal(both.confidence,'high')
  assert.equal(both.candidates[0].variantId,123)
  assert.equal(both.candidates[1].variantId,null)
  assert.equal(both.candidates[1].neuronArtwork,1)
  const missing = resolveMatch({local:[],neuron:[{konamiId:'900',neuronArtwork:1,score:.99}]},[],map)
  assert.deepEqual(missing,{confidence:'unmatched',candidates:[]})
  const ambiguous = resolveMatch({local:[{position:0,score:.80}],neuron:[{konamiId:'900',neuronArtwork:1,score:.89}]},refs,map)
  assert.equal(ambiguous.confidence,'review')
})
test('equidistant but different illustrations of one card stay separate until source features agree', () => {
  const source = (color,art) => ({card:{konamiId:'4041',neuronArtwork:art},descriptor:new Uint8Array(108).fill(color)})
  const first = source(102,1), second = source(154,2)
  const local = [{card:{konamiId:'4041',position:0},descriptor:new Uint8Array(108).fill(152)}]
  const query = new Uint8Array(108).fill(128)
  const localHits = rankArt(query,local).candidates
  const official = rankArt(query,[first,second]).candidates
  // Both official paintings have score .74 against this ambiguous screenshot.
  assert.equal(official[0].score,official[1].score)
  assert.equal(matchingLocalPosition(first,[first,second],localHits,local),null)
  assert.equal(matchingLocalPosition(second,[first,second],localHits,local),0)
  const refs = [{card:{cardId:31,variantId:105,konamiId:'4041'}}]
  const ids = new Map([['4041',{cardId:31,konamiId:'4041',artworks:{1:'first.png',2:'second.png'}}]])
  const hits = official.map((hit,i) => ({...hit,localPosition:matchingLocalPosition(
    [first,second][i],[first,second],localHits,local)}))
  const result = resolveMatch({local:localHits,neuron:hits},refs,ids)
  assert.equal(result.candidates.length,2)
  assert.equal(result.candidates.find(x=>x.variantId===105).neuronArtwork,2)
  assert.equal(result.candidates.find(x=>x.neuronArtwork===1).variantId,null)
  const tie = source(152,3)
  assert.equal(matchingLocalPosition(second,[first,second,tie],localHits,local),null)
})
test('quantity groups confirmed artwork within sections and keeps unresolved and alternative rows', () => {
  const row = {section:'MAIN',quantity:1,confidence:'high',candidates:[{konamiId:'4041',neuronArtwork:1}]}
  const data = [row,row,{...row,section:'SIDE'}, {...row,confidence:'review'},
    {...row,candidates:[{konamiId:'4041',neuronArtwork:2}]}]
  assert.deepEqual(mergeConfirmedRows(data).map(r=>r.quantity),[2,1,1,1])
  assert.equal(row.quantity,1)
})
test('editable filename titles preserve Korean/Japanese and skip system capture names', () => {
  for (const [name,want] of [['빛의 창조신.png','빛의 창조신'],['ホルアクティ.jpg','ホルアクティ'],
       ['Screenshot_20261127.jpg',''],['스크린샷 2026.png',''],['20261127.png',''],['251ec87a-02de-47ca-bb33-a357ff9925c4.webp','']]) {
    assert.equal(captureFileTitle(name),want)
  }
})
test('art signature matches the given pixels and measures ambiguity', () => {
  const img = recipe([10])
  const a = describeArt(img,{x:5,y:22,w:32,h:47})
  const tied = rankArt(a,[{card:{id:1},descriptor:a},{card:{id:2},descriptor:a}])
  assert.equal(tied.confidence,'review')
  assert.equal(tied.candidates[0].score,1)
})
