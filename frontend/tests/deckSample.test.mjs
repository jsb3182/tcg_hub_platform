import test from 'node:test'
import assert from 'node:assert/strict'
import {curve,drawableEntries,openingHand,openingSizes} from '../src/deckSample.js'

const main=(cardId,quantity,curveValue)=>({cardId,section:'MAIN',quantity,curveValue})

test('each game has an opening size; setup sections stay out of the draw pile',()=>{
  assert.deepEqual(openingSizes,{YUGIOH:5,POKEMON:7,ONEPIECE:5,WEISS:5,NIVEL:5,RIFTBOUND:4})
  const saved=main(1,3,0)
  const excluded=['SIDE','EXTRA','LEADER','DON','RUNE','CHAMPION','LEGEND','BATTLEFIELD'].map(section=>({...saved,section}))
  assert.deepEqual(drawableEntries([saved,...excluded,main(3,0,1),main(4,2.5,1)]),[saved])
})

test('curve weights by quantity; missing and invalid values are separate from a verified zero',()=>{
  assert.deepEqual(curve([main(1,3,4),main(2,2,0),main(3,1,4),main(4,3,null),main(5,2,undefined)]),
    {bins:[[0,2],[4,4]],unknown:5})
})

test('sampling without replacement preserves quantities and deck contents',()=>{
  const entries=[main(10,2,0),main(20,3,4)]
  const byId=items=>items.map(e=>e.cardId)
  assert.deepEqual(byId(openingHand(entries,3,()=>0)),[10,10,20])
  assert.deepEqual(byId(openingHand(entries,7,()=>0.9999)),[20,20,20,10,10])
  assert.deepEqual(entries.map(e=>e.quantity),[2,3])
  assert.deepEqual(openingHand(entries,0),[])
  assert.deepEqual(openingHand([],7),[])
})
