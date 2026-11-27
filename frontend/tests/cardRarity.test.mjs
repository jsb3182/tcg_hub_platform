import test from 'node:test'
import assert from 'node:assert/strict'
import {rarityBadges} from '../src/cardRarity.js'

test('the legacy DBGV printing keeps three distinct rarities in the chosen language',()=>{
  const card={gameCode:'YUGIOH',rarity:'UR SE PSE',variants:[{rarity:'Ultra Rare'}]}
  assert.deepEqual(rarityBadges(card,'ko').map(b=>b.label),['울트라 레어','시크릿 레어','프리즈마틱 시크릿 레어'])
  assert.equal(rarityBadges(card,'en')[1].label,'Secret Rare')
  assert.equal(rarityBadges(card,'ja')[2].label,'プリズマティックシークレットレア')
})
test('publisher codes are not expanded using a different game’s dictionary',()=>{
  assert.deepEqual(rarityBadges({gameCode:'WEISS',rarity:'SR'},'en'),[{code:'SR',label:''}])
  assert.deepEqual(rarityBadges({gameCode:'POKEMON',rarity:'Uncommon'},'ja'),[{code:'',label:'アンコモン'}])
  assert.deepEqual(rarityBadges({rarity:'未確認の種類',language:'en',specs:{language:'ja'}},'en'),[])
})
