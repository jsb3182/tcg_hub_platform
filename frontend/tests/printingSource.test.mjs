import assert from 'node:assert/strict'
import test from 'node:test'
import { printingSource } from '../src/printingSource.js'

const pokemon = {gameCode:'POKEMON', packName:'Unseen Forces Unown Collection', originalName:'Unown'}
const bang = {...pokemon, number:'!', sourceUrl:'https://api.tcgdex.net/v2/en/cards/exu-%21'}
const question = {...pokemon, number:'%3F', sourceUrl:'https://api.tcgdex.net/v2/en/cards/exu-%253F'}

test('the two English Unown scans retain their distinct printed symbols and source pages', () => {
  assert.deepEqual(printingSource(bang),{url:'https://pkmncards.com/card/unown-unseen-forces-uf-2/',label:'영문 인쇄본',provider:'PkmnCards',number:'!/28'})
  assert.deepEqual(printingSource(question),{url:'https://pkmncards.com/card/unown-unseen-forces-uf/',label:'영문 인쇄본',provider:'PkmnCards',number:'?/28'})
  assert.deepEqual(printingSource({...question,number:'?'}),printingSource(question))
  for(const card of [{...bang,number:'%3F'},{...question,number:'!'},{...bang,originalName:'Unown V'},
    {...question,packName:'Unseen Forces'},{...bang,gameCode:'WEISS'},{...question,sourceUrl:question.sourceUrl+'?foo'},
    {...question,sourceUrl:question.sourceUrl.replace('.net','.net.example')},{...bang,sourceUrl:null}]) {
    assert.equal(printingSource(card),null)
  }
})

test('only the exact same English Bushiroad printing page is linked', () => {
  const number='SAO/S47-E001', url='https://en.ws-tcg.com/cardlist/?cardno=SAO%2FS47-E001'
  const printing = candidate => printingSource({gameCode:'WEISS',number,specs:{publisherCardUrl:candidate}})
  assert.deepEqual(printing(url),{url,label:'발행사 영문 카드 페이지'})
  for(const candidate of [undefined,'javascript:alert(1)',url.replace('https:','http:'),url.replace('.com/','.com.attacker.example/'),
    url.replace('.com/','.com@attacker.example/'),url.replace('cardlist/','images/'),url.replace('001','002'),
    url+'&cardno=other',url+'#anything',url+'&redirect=https://attacker.example',url+'%0D']) {
    assert.equal(printing(candidate),null)
  }
})

test('four English gold DON!! finishes link only to their exact TCGplayer listing', () => {
  const sourceUrl='https://optcgapi.com/api/allDonCards/'
  for (const [number,pack,subject,productId] of [
    ['DON:don_132','EB-03','Boa Hancock',677571], ['DON:don_169','PRB-02','Rob Lucci',655121],
    ['DON:don_181','EB-03','Uta',677567], ['DON:don_185','OP-16','Alternate Art',698314]
  ]) {
    const name='DON!! Card ('+subject+') (Gold)'
    const card={gameCode:'ONEPIECE',number,productCode:pack,originalName:name,sourceUrl,
      specs:{productCode:pack,names:{en:name}}}
    const reference=printingSource(card)
    assert.equal(new URL(reference.url).origin,'https://www.tcgplayer.com')
    assert.equal(new URL(reference.url).pathname.split('/')[2],String(productId))
    assert.equal(reference.provider,'TCGplayer')
    assert.equal(reference.label,'영문 인쇄본')
    for (const incorrect of [{...card,number:number==='DON:don_132'?'DON:don_181':'DON:don_132'}, {...card,number:'DON:don_999'},
      {...card,gameCode:'POKEMON'}, {...card,productCode:'PRB-01'}, {...card,specs:{...card.specs,productCode:'PRB-01'}},
      {...card,originalName:name.replace(' (Gold)','')}, {...card,specs:{...card.specs,names:{en:'Other artwork'}}},
      {...card,sourceUrl:'https://optcgapi.com.example/api/allDonCards/'}]) {
      assert.equal(printingSource(incorrect),null)
    }
  }
})

test('Riot English gallery requires publisher evidence for the exact printing and shows its published number', () => {
  const url = 'https://playriftbound.com/en-us/card-gallery/'
  const ref = (number, publicCode, extra = {}, gameCode = 'RIFTBOUND') =>
    printingSource({gameCode,number,specs:{editionEvidence:{en:{source:url,basis:'PUBLISHER_PRINTING',publicCode,...extra}}}})
  for (const [number,code] of [['ogn-001-298','OGN-001/298'],['ogn-303*-298','OGN-303*/298'],
    ['rad-r01a','RAD-R01a'],['ven-sp1-006','VEN-SP1/006']]) {
    assert.deepEqual(ref(number,code),{url,label:'Riot 영문 카드 갤러리',number:code})
  }
  assert.equal(ref('ogn-303-298','OGN-303*/298'),null)
  assert.equal(ref('sfd-001-221','OGN-001/298'),null)
  assert.equal(ref('ogn-001-298','OGN-001/298',{basis:'SOURCE_LABEL'}),null)
  assert.equal(ref('ogn-001-298','OGN-001/298',{source:url+'?card=other'}),null)
  assert.equal(ref('ogn-001-298','OGN-001/298',{source:url.replace('.com/','.com.example/')}),null)
  assert.equal(ref('ogn-001-298','OGN-001/298',{},'ONEPIECE'),null)
  assert.equal(ref('ogn-<img>-298','OGN-<img>/298'),null)
  assert.equal(printingSource({gameCode:'RIFTBOUND',number:'ogn-001-298',specs:{}}),null)
})
