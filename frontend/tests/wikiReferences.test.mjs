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
