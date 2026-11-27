import assert from 'node:assert/strict'
import test from 'node:test'
import {cardWikiReferences,namuArticleUrl} from '../src/wikiReferences.js'

test('only HTTPS NamuWiki article URLs are usable',()=>{
  const article='https://namu.wiki/w/테스트 문서/카드#s-2'
  assert.equal(namuArticleUrl(article),new URL(article).href)
  for(const url of [null,12,'/w/카드','http://namu.wiki/w/카드','https://namu.wiki/Search?q=카드',
    'https://namu.wiki/w/','https://namu.wiki/w/%20','https://namu.wiki/w/%xx',
    'https://example.invalid/w/카드','https://namu.wiki.example.invalid/w/카드',
    'https://someone@namu.wiki/w/카드','https://namu.wiki:8080/w/카드','https://namu.wiki/w/%00']){
    assert.equal(namuArticleUrl(url),'')
  }
})

test('only accepted card-scoped references render; snapshots and revisions are independent',()=>{
  const original={language:'ko',title:'테스트 문서',url:'https://namu.wiki/w/테스트 문서',revision:null,snapshotDate:'2024-01-02'}
  assert.deepEqual(cardWikiReferences({names:{ko:'테스트 문서'}}),[])
  const rows=cardWikiReferences({wikiReferences:[null,original,{...original},{...original,url:'https://example.invalid/'},
    {...original,language:'en'},{...original,title:''},{...original,revision:315,snapshotDate:null}]})
  assert.equal(rows.length,2);assert.equal(rows[0].revision,'');assert.equal(rows[0].snapshotDate,'2024-01-02')
  assert.equal(rows[1].revision,'315');assert.equal(rows[1].snapshotDate,'')
})

test('snapshot link must be pinned to the named distribution',()=>{
  const prefix='https://huggingface.co/datasets/Bingsu/namuwiki_20210301_filtered/tree/'
  const hash='0123456789abcdef0123456789abcdef01234567'
  const ref=snapshotUrl=>cardWikiReferences({wikiReferences:[{url:'https://namu.wiki/w/문서',title:'문서',language:'ko',snapshotUrl}]})[0]
  assert.equal(ref(prefix+hash).snapshotUrl,prefix+hash)
  for(const url of [prefix+'main',prefix.replace('Bingsu','other')+hash,prefix.replace('.co/','.co.example.invalid/')+hash])assert.equal(ref(url).snapshotUrl,'')
})

test('card sources keep only named wiki details and plain article text',()=>{
  const [r]=cardWikiReferences({wikiReferences:[{url:'https://namu.wiki/w/test',language:'ko',title:'test',textKo:'<em>문서 요약</em>',
    details:{packs:['수록 상품','수록 상품',false],traits:[null,'빛 속성'],rulings:'bad',other:['hidden']}}]})
  assert.equal(r.textKo,'<em>문서 요약</em>')
  assert.deepEqual(r.details,{traits:['빛 속성'],packs:['수록 상품']})
})

const reference={language:'ko',title:'카드',url:'https://namu.wiki/w/카드',snapshotDate:'2026-08-29'}
function renderedLink(game,url){
  return cardWikiReferences({wikiReferences:[{...reference,verificationUrl:url}]},game)[0].verificationUrl
}

test('the August 2026 snapshot points to its fixed Archive item',()=>{
  const item='https://archive.org/details/namuwiki-data-dump-20260829'
  const render=(snapshotUrl,snapshotDate=reference.snapshotDate)=>
    cardWikiReferences({wikiReferences:[{...reference,snapshotDate,snapshotUrl}]})[0].snapshotUrl
  assert.equal(render(item),item)
  assert.equal(render(item,'2026-08-28'),'')
  for(const other of [item+'0',item+'?q=else',item+'#files',item.replace('/details/','/download/'),
    item.replace('archive.org','archive.org.example.invalid'),item.replace('https:','http:')]) assert.equal(render(other),'')
})

test('each game retains its verified publisher card or product link',()=>{
  const links={
    YUGIOH:['https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=4711&request_locale=ko'],
    POKEMON:['https://pokemoncard.co.kr/cards/detail/BS2014001001'],
    ONEPIECE:[
      'https://www.onepiece-cardgame.kr/cardlist.do?blockIcons=&categories=&colors=&freewords=ST01-001&illustrations=&page=0&series=all&size=20',
      'https://onepiece-cardgame.kr/cardlist.do?categories=&colors=&freewords=OP01-003&illustrations=&series=all',
      'https://onepiece-cardgame.kr/products/view.do?brdno=236','https://www.onepiece-cardgame.kr/products/view.do?brdno=481',
    ],
    NIVEL:['http://nivelarena.co.kr/bbs/board.php?bo_table=cardlists&wr_id=664'],
  }
  for(const [game,urls] of Object.entries(links)){
    for(const url of urls){
      assert.equal(renderedLink(game,url),url)
      for(const other of Object.keys(links).filter(key=>key!==game))assert.equal(renderedLink(other,url),'')
    }
  }
})

test('publisher origins, card identifiers and allowed query fields are checked',()=>{
  const op='https://www.onepiece-cardgame.kr'
  for(const url of [
    op+'/cardlist.do',op+'/cardlist.do?freewords=search',op+'/cardlist.do?freewords=ST01-001&freewords=OP01-003',
    op+'/cardlist.do?freewords=ST01-001&next=https://example.invalid',op+'/cardlist.do?freewords=ST01-001#other',
    op+'/products/view.do?brdno=0',op+'/topics/view.do?brdno=236',op+'/products/view.do?brdno=236&next=/',
    'http://www.onepiece-cardgame.kr/products/view.do?brdno=236','https://www.onepiece-cardgame.kr.example.invalid/products/view.do?brdno=236',
    'https://visitor@www.onepiece-cardgame.kr/products/view.do?brdno=236',
  ])assert.equal(renderedLink('ONEPIECE',url),'')
  const nivel='http://nivelarena.co.kr/bbs/board.php'
  for(const url of [nivel+'?bo_table=notice&wr_id=664',nivel+'?bo_table=cardlists',
    nivel+'?bo_table=cardlists&wr_id=664&wr_id=1291',nivel+'?bo_table=cardlists&wr_id=-1',
    nivel+'?bo_table=cardlists&wr_id=664&url=https://example.invalid',
    nivel.replace('nivelarena.co.kr','nivelarena.co.kr.example.invalid')+'?bo_table=cardlists&wr_id=664'])assert.equal(renderedLink('NIVEL',url),'')
})
