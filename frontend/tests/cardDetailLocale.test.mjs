import assert from 'node:assert/strict'
import test from 'node:test'
import { cardDetailLocale } from '../src/cardDetailLocale.js'

function facts(card, lang) {
  return Object.fromEntries(cardDetailLocale(card, lang).facts.map(f => [f.key, [f.label, f.value]]))
}

test('each field requires its own language and retains only the credit for that field', () => {
  const card = {
    gameCode:'YUGIOH', name:'국내 도감 표기', language:'ko', nameBasis:'IMPORTED_LABEL',
    nameReferenceUrl:'https://example.org/ko', effect:'日本語の効果', effectLanguage:'ja',
    effectBasis:'REVIEWED_PRINTING', effectReferenceUrl:'https://example.org/ja',
    originalName:'原語', specs:{ej:1}, imageLanguage:'en', imageUrl:'https://example.org/en.webp',
    variants:[{image:{language:'ja', url:'/media/sheets/fixture.webp'}}],
  }
  const ko = cardDetailLocale(card, 'ko')
  assert.equal(ko.name, card.name)
  assert.equal(ko.nameReferenceUrl, card.nameReferenceUrl)
  assert.equal(ko.effect, null)
  assert.equal(ko.effectLanguage, null)
  assert.equal(ko.effectReferenceUrl, null)
  assert.equal(ko.imageLanguage, null)
  const ja = cardDetailLocale(card, 'ja')
  assert.equal(ja.name, null)
  assert.equal(ja.nameBasis, null)
  assert.equal(ja.effect, card.effect)
  assert.equal(ja.effectBasis, 'REVIEWED_PRINTING')
  assert.equal(ja.imageLanguage, 'ja')
  const en = cardDetailLocale(card, 'en')
  assert.equal(en.imageLanguage, 'en')
  assert.equal(en.name, null)
  assert.equal(en.effect, null)
})

test('explicit editions work independently on old payloads and a reviewed field wins', () => {
  const card = {name:'Fallback', effect:'Original English rules', specs:{
    names:{ko:'한국어 판본', ja:'日本語の参考名'}, texts:{ja:'日本語の効果'}, sources:{ja:'https://example.org/edition'},
    nameBasis:{ja:'RELATED_PRINTING'}, images:{ko:'https://example.org/ko.webp'},
  }}
  assert.equal(cardDetailLocale(card,'ko').name, '한국어 판본')
  assert.equal(cardDetailLocale(card,'ko').effect, null)
  assert.equal(cardDetailLocale(card,'ko').imageLanguage, 'ko')
  assert.equal(cardDetailLocale(card,'ja').nameBasis, 'RELATED_PRINTING')
  assert.equal(cardDetailLocale(card,'ja').effectReferenceUrl, card.specs.sources.ja)
  assert.equal(cardDetailLocale(card,'en').name, null)
  const reviewed = cardDetailLocale({...card, name:'校正済み', language:'ja', nameBasis:'TRANSLATED_NAME'}, 'ja')
  assert.equal(reviewed.name, '校正済み')
  assert.equal(reviewed.nameBasis, 'TRANSLATED_NAME')
  assert.equal(reviewed.nameReferenceUrl, null)
  assert.equal(reviewed.effect, '日本語の効果')
})

test('DBGV-JP001 legacy metadata has a localized kind, attribute, subtype, race and numeric stats', () => {
  const card = {gameCode:'YUGIOH', number:'DBGV-JP001', specs:{
    k:'몬스터', at:'빛', lv:4, rc:'언데드족', sub:'효과', atk:0, def:1000,
    nw:'신규', or:'せねと', sources:{ja:'https://example.org'}, texts:{en:{untrusted:'value'}},
    editionEvidence:{privateIndex:'fixture'}, language:'ko',
  }}
  assert.deepEqual(facts(card,'en'), {
    type:['Card type','Monster'], subtype:['Subtype','Effect'], attribute:['Attribute','Light'],
    race:['Monster type','Zombie'], level:['Level','4'], atk:['ATK','0'], def:['DEF','1000'],
  })
  assert.deepEqual(facts(card,'ja').race, ['種族','アンデット族'])
  assert.equal(cardDetailLocale(card,'en').effect, null)
  assert.equal(cardDetailLocale(card,'ja').name, null)
  assert.deepEqual(facts({gameCode:'YUGIOH',specs:{k:'몬스터',sub:'엑시즈 / 효과',lv:7}},'ja').rank, ['ランク','7'])
  const link = facts({gameCode:'YUGIOH',specs:{type:'Link Monster',linkval:2,linkmarkers:['Bottom-Left','Bottom-Right']}},'ko')
  assert.deepEqual(link.link, ['링크','2'])
  assert.deepEqual(link.markers, ['링크 마커','↙↘'])
  assert.equal(link.level, undefined)
})

test('only curated structural values are exposed for all six publishers', () => {
  const poke={gameCode:'POKEMON',specs:{hp:80,types:['Grass'],retreat:2,pokedex_number:1,
    attacks:[{name:'외국어 공격명',effect:'숨길 텍스트'}], referenceNames:{ko:'다른 카드'}}}
  assert.deepEqual(facts(poke,'ja'), {hp:['HP','80'],energyType:['タイプ','草'],retreat:['にげるためのエネルギー','2'],pokedex:['全国図鑑番号','1']})
  const ws={gameCode:'WEISS',specs:{color:'YELLOW',type:'Character',level:0,cost:'0',power:1500,soul:1,attributes:['Music']}}
  assert.deepEqual(facts(ws,'ja').type, ['カード種類','キャラ'])
  assert.deepEqual(facts(ws,'ko').level, ['레벨','0'])
  const rift={gameCode:'RIFTBOUND',specs:{type:'Unit',energy:4,power:1,might:4,domains:['Fury'],editionEvidence:{token:'omit'}}}
  assert.deepEqual(facts(rift,'ko'),{energy:['에너지','4'],might:['위력','4'],runePower:['힘','1']})
  const op={gameCode:'ONEPIECE',specs:{type:'leader',colors:['red','green'],life:'4',cost:'',power:5000,cleanName:'omit'}}
  assert.deepEqual(facts(op,'ja'), {type:['カード種類','リーダー'],color:['色','赤 / 緑'],power:['パワー','5000'],life:['ライフ','4']})
  const nivel={gameCode:'NIVEL',specs:{language:'ko',type:'아이템',attribute:'화염',코스트:'2',파워:'-',히트:'-',키워드:'어태커',IP:'제목'}}
  assert.deepEqual(facts(nivel,'en'), {type:['Card type','Item'],attribute:['Attribute','Flame'],cost:['Cost','2']})
  assert.deepEqual(facts(nivel,'ko').type,['종류','아이템'])
  assert.equal(facts({gameCode:'NIVEL', specs:{type:'unknown label',attribute:{nested:'source'}}},'ko').type, undefined)
})

test('unknown language, arbitrary nested specs and unclassified images remain unavailable', () => {
  const card={gameCode:'YUGIOH', name:'한국어처럼 보여도 언어 미확인', language:'und', effect:'ABC', originalName:'Original',
    specs:{type:{not:'a label'}, atk:{value:'7'}, def:'attacker', images:[], or:'foreign text', passcode:111},
    variants:[{image:{language:null,url:'/media/sheets/unknown.webp'}}]}
  for (const lang of ['ko','en','ja','it',null]) {
    const detail=cardDetailLocale(card,lang)
    assert.deepEqual(detail.facts,[])
    assert.ok(Object.entries(detail).every(([k,v])=>k==='facts' || v===null))
  }
})
