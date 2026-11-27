// Run against a production build. All account, deck and regional-list responses are local fixtures.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, readFile } from 'node:fs/promises'
import { extname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=fileURLToPath(new URL('../dist/',import.meta.url)), origin='http://127.0.0.1:19894'
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png'}
const names={ko:'시험 카드',en:'Test card',ja:'試験カード'}
const tile=(col,language)=>({sheetId:1,url:'/media/test-sheet.png',row:0,col,cellWidth:25,cellHeight:36,language})
const card=(id,lang)=>({id,name:names[lang]+id,number:'QA-'+id,language:lang,gameCode:'YUGIOH',
  image:tile({ko:1,en:2,ja:3}[lang],lang),effect:names[lang]+'!',effectLanguage:lang})
const rows=[
  {cardId:11,section:'MAIN',quantity:2,variantId:101,image:tile(0,'en')},
  {cardId:11,section:'MAIN',quantity:1,variantId:102,image:tile(3,'ja')},
  {cardId:12,section:'MAIN',quantity:1,neuronArtwork:4,imageBasis:'SELECTED_ARTWORK',imageLanguage:'ja',imageUrl:'/media/neuron4.png'},
  {cardId:12,section:'MAIN',quantity:1,neuronArtwork:7,imageBasis:'SELECTED_ARTWORK',imageUrl:null},
  {cardId:12,section:'MAIN',quantity:1},
  {cardId:13,section:'SIDE',quantity:2},
]
const rule={version:1,regions:['OCG','TCG'],sections:[{section:'MAIN',minCards:40,maxCards:60},{section:'SIDE',minCards:0,maxCards:15}]}
const source='https://www.db.yugioh-card.com/yugiohdb/forbidden_limited.action'
function report(region,status,violations=[],unknownCardIds=[]){
  return {region,status,sourceUrl:source,effectiveOn:status==='UNAVAILABLE'?null:'2026-10-01',violations,unknownCardIds}
}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
try{
 for(const width of [360,1280]){
  const ctx=await browser.newContext({viewport:{width,height:850},isMobile:width===360,hasTouch:width===360,serviceWorkers:'block'})
  const page=await ctx.newPage(),errors=[],writes=[],checks=[],modes=new Map()
  page.setDefaultTimeout(5500)
  page.on('pageerror',e=>errors.push(e.message))
  const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=100;c.height=108
    const g=c.getContext('2d');['#b11','#252','#558','#c93'].forEach((color,i)=>{g.fillStyle=color;g.fillRect(i*25,0,25,36)})
    return c.toDataURL('image/png').split(',')[1]})
  let savedRegion=null,legacy=false,nextFailure=false
  const deck=lang=>({id:51,gameCode:'YUGIOH',name:'QA',revision:1,state:'DRAFT',region:savedRegion,
    entries:rows.map(r=>({...card(r.cardId,lang),...r})),rule:legacy?{...rule,regions:undefined}:rule,
    regionalLimits:savedRegion?report(savedRegion,'CHECKED'):null})
  await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url()),path=url.pathname,lang=url.searchParams.get('lang')||'ko'
    if(url.origin!==origin)return route.abort()
    const json=(value,status=200)=>route.fulfill({json:value,status})
    if(path.startsWith('/media/'))return route.fulfill({contentType:'image/png',body:Buffer.from(png,'base64')})
    if(path==='/api/v1/auth/refresh')return json({email:'deck@example.invalid',accessToken:'fixture',role:'ROLE_USER'})
    if(path==='/api/v1/auth/admin-mode')return json({mode:'DISABLED'})
    if(path==='/api/v1/games')return json([{code:'YUGIOH',name:'유희왕'}])
    if(path==='/api/v1/me/decks/yugioh-limits'){
      assert.equal(req.headers().authorization,'Bearer fixture')
      const body=req.postDataJSON();checks.push(body)
      if(nextFailure){nextFailure=false;return json({},503)}
      return json(modes.get(body.region)||report(body.region,'CHECKED'))
    }
    if(path==='/api/v1/me/decks/51'){
      if(req.method()==='PUT'){const body=req.postDataJSON();writes.push(body);savedRegion=body.region||null}
      return json(deck(lang))
    }
    if(path==='/api/v1/shared/decks/fixture')return json({...deck(lang),region:'TCG',regionalLimits:report('TCG','PARTIAL',[],[11])})
    if(path==='/api/v1/me/decks/needed')return json({items:[],next:null})
    if(path==='/api/v1/play/cards'){
      const ids=url.searchParams.get('ids');if(ids)assert.equal(new Set(ids.split(',')).size,ids.split(',').length)
      return json((ids?ids.split(',').map(Number):[11,12]).map(id=>card(id,lang)))
    }
    if(path==='/api/v1/cards')return json({items:[11,12,13].map(id=>card(id,lang)),total:3})
    if(path.startsWith('/api/'))return json([])
    const f=extname(path)?path.slice(1):'index.html'
    return route.fulfill({contentType:mime[extname(f)],body:await readFile(resolve(dist,f))})
  })
  const go=path=>page.goto(origin+path),lng=page.locator('.locale-switch select')
  const layout=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  async function capture(name,target){
    if(!process.env.QA_SCREENSHOTS)return
    await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
    await target.scrollIntoViewIfNeeded()
    await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,name+'-'+width+'.png')})
  }
  const visible=locator=>locator.first().waitFor({state:'visible'})
  const setup=page.locator('.practice-setup .play-list'),zones=page.locator('.practice-zones section')
  const count=async(locator,n)=>{await locator.nth(n-1).waitFor({state:'attached'});assert.equal(await locator.count(),n)}
  const setupRows=setup.locator('li')
  await go('/play?game=YUGIOH&deck=51&lang=ko')
  await count(setupRows,5)
  assert.match(await setupRows.nth(0).innerText(),/× 2/)
  assert.match(await setupRows.nth(1).innerText(),/× 1/)
  assert.equal(await setupRows.nth(0).locator('.lib-thumbnail').evaluate(e=>e.style.backgroundPosition),'0% 0%')
  assert.equal(await setupRows.nth(1).locator('.lib-thumbnail').evaluate(e=>e.style.backgroundPosition),'100% 0%')
  await visible(setupRows.nth(2).locator('img[src$="/neuron4.png"]'))
  assert.match(await setupRows.nth(3).innerText(),/이미지 없음/)
  await setupRows.nth(4).getByRole('button').click()
  await count(setupRows,4)
  await page.locator('.play-hits li').nth(1).getByRole('button').click()
  await count(setupRows,5)
  await page.getByRole('button',{name:'섞고 시작'}).click()
  await page.getByRole('button',{name:'한 장 뽑기'}).click()
  const hand=zones.nth(0).locator('li'),field=zones.nth(1).locator('li'),discard=zones.nth(2).locator('li')
  await count(hand,6)
  const first=hand.filter({hasText:'저장한 그림 1'})
  await count(first,2)
  await first.first().getByRole('button',{name:'테이블에 놓기'}).click()
  await visible(field.filter({hasText:'저장한 그림 1'}))
  await capture('practice-artwork',field.first())
  const artOf=locator=>locator.locator('.lib-thumbnail').evaluate(e=>e.style.backgroundPosition)
  assert.equal(await artOf(field.first()),'0% 0%')
  for(const [lang,art,missing] of [['en','Saved artwork','No image'],['ja','保存したイラスト','画像なし'],['ko','저장한 그림','이미지 없음']]){
    await lng.selectOption(lang)
    await visible(field.getByText(names[lang]+'11',{exact:true}))
    await visible(field.getByText(art+' 1',{exact:true}))
    assert.equal(await artOf(field.first()),'0% 0%')
    assert.equal(await artOf(hand.filter({hasText:art+' 2'})),'100% 0%')
    await visible(hand.locator('img[src$="/neuron4.png"]'))
    const missingRow=hand.filter({hasText:missing});await visible(missingRow)
    assert.equal(await missingRow.locator('.lib-thumbnail').count(),0)
    const generic=hand.filter({has:page.getByText(names[lang]+'12',{exact:true})}).filter({hasNot:page.locator('small').filter({hasText:/뉴런 일러스트|Neuron artwork|ニューロンのイラスト/})})
    assert.equal(await artOf(generic),{'ko':'33.3333% 0%','en':'66.6667% 0%','ja':'100% 0%'}[lang])
    await layout()
  }
  await field.getByRole('button',{name:'버리기'}).click()
  assert.equal(await artOf(discard.first()),'0% 0%')
  await discard.getByRole('button',{name:'손으로 가져오기'}).click();await count(hand,6)
  await page.getByRole('button',{name:'다시 섞기'}).click();await count(hand,5)
  await page.getByRole('button',{name:'한 장 뽑기'}).click();await count(hand,6);await count(first,2)
  await page.reload();await count(setupRows,5)
  assert.equal(await zones.count(),0)
  await go('/decks/51?lang=ko')
  const panel=page.locator('.regional-limits'),selector=panel.locator('select'),complete=page.getByRole('button',{name:'구성 완료 저장'})
  await visible(selector);assert.equal(checks.length,0)
  const issues=[0,1,2].map((limit,i)=>({cardId:11+i,name:'Original',limit,copies:3}))
  modes.set('OCG',report('OCG','PARTIAL',issues,[13]))
  await selector.selectOption('OCG')
  await visible(panel.getByText('미확인 카드 (1)'))
  assert.deepEqual(await panel.locator('.limits-list strong').allTextContents(),['금지 · 시험 카드11','제한 · 시험 카드12','준제한 · 시험 카드13'])
  assert.equal(await panel.getByRole('link').getAttribute('href'),source)
  assert.equal(await panel.locator('time').textContent(),'2026-10-01')
  assert.equal(await complete.isDisabled(),true)
  assert.deepEqual(checks[0].entries.map(e=>[e.cardId,e.variantId??null,e.neuronArtwork??null,e.quantity]),rows.map(e=>[e.cardId,e.variantId??null,e.neuronArtwork??null,e.quantity]))
  await panel.locator('summary').click();await visible(panel.locator('details li').getByText('시험 카드13'))
  await layout();await capture('regional-limits',panel)
  const quantity=page.locator('.lib-controls input').first()
  await quantity.fill('');await visible(panel.getByText('수량을 입력하면 목록을 확인합니다.'))
  const checkedNewAmount=page.waitForResponse(r=>r.url().endsWith('/yugioh-limits') && r.request().postDataJSON().entries[0].quantity===1)
  await quantity.fill('1');await checkedNewAmount;await visible(panel.locator('.limits-list strong'))
  await lng.selectOption('en');await visible(panel.getByText('Forbidden · Test card11'))
  await lng.selectOption('ja');await visible(panel.getByText('禁止 · 試験カード11'))
  await lng.selectOption('ko');await visible(panel.getByText('금지 · 시험 카드11'))
  await page.getByRole('button',{name:'임시 저장',exact:true}).click()
  await visible(page.getByText('작성 중 상태로 저장했습니다.',{exact:true}))
  assert.equal(writes[writes.length-1].region,'OCG');assert.equal(writes[writes.length-1].state,'DRAFT')
  modes.set('TCG',report('TCG','UNAVAILABLE'));await selector.selectOption('TCG')
  await visible(panel.getByText('이 지역의 목록을 확인할 수 없습니다.'));assert.equal(await complete.isDisabled(),true)
  assert.equal(await panel.locator('time').count(),0)
  nextFailure=true;modes.delete('OCG');await selector.selectOption('OCG')
  await visible(panel.getByRole('button',{name:'다시 확인'}));await panel.getByRole('button',{name:'다시 확인'}).click()
  await visible(panel.getByText('목록에서 수량 초과가 발견되지 않았습니다.'))
  assert.equal(await complete.isDisabled(),false)
  await layout()
  await selector.selectOption('');await page.getByRole('button',{name:'임시 저장',exact:true}).click()
  await visible(page.getByText('작성 중 상태로 저장했습니다.',{exact:true}))
  assert.equal(writes[writes.length-1].region,'')
  const before=checks.length
  await go('/shared/decks/fixture?lang=ja')
  await visible(panel.getByText('未確認のカード (1)'));assert.equal(await panel.locator('select').count(),0)
  assert.equal(checks.length,before)
  legacy=true
  await go('/decks/51?lang=ko')
  await visible(complete);assert.equal(await panel.count(),0)
  await page.getByRole('button',{name:'임시 저장',exact:true}).click()
  await visible(page.getByText('작성 중 상태로 저장했습니다.',{exact:true}))
  assert.equal('region' in writes[writes.length-1],false);assert.equal(checks.length,before)
  assert.deepEqual(errors,[])
  console.log(width+'px · saved artwork, three languages, piles, regional reports, drafts, shared deck and legacy server OK')
  await ctx.close()
 }
}finally{await browser.close()}
