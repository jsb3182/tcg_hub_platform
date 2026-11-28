// Build first. RELEASE_QA_ORIGIN selects a loopback Spring service with calendar data for each game.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=process.env.RELEASE_QA_DIST||fileURLToPath(new URL('../dist/',import.meta.url)),actual=process.env.RELEASE_QA_ORIGIN
const origin=actual||'http://127.0.0.1:19899'
assert.equal(new URL(origin).hostname,'127.0.0.1')
const codes=['YUGIOH','POKEMON','WEISS','NIVEL','RIFTBOUND','ONEPIECE'],regions=['NA','EN','JP','KR','GLOBAL','CN']
const day='2026-11-27', size=24
const events=Array.from({length:186},(_,i)=>{
  const j=i%codes.length,id=i+1,releaseDate=new Date(Date.UTC(2026,9,20+i)).toISOString().slice(0,10)
  return {id,gameCode:codes[j],region:regions[j],releaseDate,code:'QA-'+id,productKey:'product-'+id,productType:i%2?'BOOSTER':'STARTER',
    name:'시험 상품 '+id,names:{ko:'시험 상품 '+id,en:'Test set '+id,ja:'テスト商品 '+id},sourceUrl:'https://example.invalid/sets/'+id,
    catalogPackId:i%3?1000+id:null,catalogCount:i%3?1:0}
})
// These catalogued products deliberately have no dated event in this fixture.
const catalog=[['DBGV','글로리어스 빅터즈'],['SV1V','바이올렛 ex'],['SAO/S47','Sword Art Online Re: Edit'],['SB02','니벨아레나 스페셜 부스터'],['OGN','Origins'],['OP-01','ROMANCE DAWN']].map(([code,name],i)=>({id:8001+i,gameCode:codes[i],code,name,catalogCount:10+i}))
for(let i=1;i<=26;i++)catalog.push({id:8100+i,gameCode:'POKEMON',code:'QA-SERIES-'+i,name:'검색 검사 상품 '+i,catalogCount:i})
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png'}
function fixture(params){
  const period=params.get('period'),game=params.get('game'),region=params.get('region'),q=(params.get('q')||'').toLowerCase(),p=+(params.get('page')||0),packId=+params.get('packId')
  const month=params.get('month'),product=params.get('productType'),limit=Number(params.get('size')||size)
  let rows=events.filter(e=>(!game||game.split(',').includes(e.gameCode))&&(!region||region.split(',').includes(e.region))&&(!packId||e.catalogPackId===packId)&&
    (!month||e.releaseDate.startsWith(month))&&(!product||product.split(',').includes(e.productType))&&
    (period==='all'||(period==='past'?e.releaseDate<day:e.releaseDate>=day))&&
    (!q||[e.name,e.code,...Object.values(e.names)].some(n=>n.toLowerCase().includes(q))))
  rows.sort((a,b)=>(period==='past'?-1:1)*a.releaseDate.localeCompare(b.releaseDate))
  return {items:rows.slice(p*limit,(p+1)*limit),page:p,size:limit,total:rows.length,asOf:day}
}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
let nextPublicRequest=0
try{
 for(const width of [360,1280]){
  const ctx=await browser.newContext({viewport:{width,height:800},isMobile:width===360,hasTouch:width===360,serviceWorkers:'block'})
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(9000)
  await ctx.route('**/*',async route=>{
    const u=new URL(route.request().url()),path=u.pathname
    if(u.origin!==origin)return route.abort()
    if(actual && path.startsWith('/api/')){
      // Respect the shared QA service's 180 requests per minute across both viewports.
      const scheduled=Math.max(Date.now(),nextPublicRequest)
      nextPublicRequest=scheduled+450
      if(scheduled>Date.now())await new Promise(done=>setTimeout(done,scheduled-Date.now()))
    }
    if(actual && !process.env.RELEASE_LOCAL_DIST)return route.continue()
    if(actual && (path.startsWith('/api/')||path.startsWith('/media/')))return route.continue()
    const json=v=>route.fulfill({json:v})
    if(path==='/api/v1/catalog-packs'){
      const g=u.searchParams.get('game'),q=(u.searchParams.get('q')||'').toLowerCase()
      const n=Number(u.searchParams.get('page')),limit=Number(u.searchParams.get('size'))
      const matches=catalog.filter(p=>(!g||g===p.gameCode)&&(p.code+' '+p.name).toLowerCase().includes(q))
      return json({items:matches.slice(n*limit,(n+1)*limit),total:matches.length})
    }
    if(path==='/api/v1/release-calendar' && u.searchParams.get('packId')==='9900'){
      return json({items:[{id:1,catalogPackId:9901,region:'KR',releaseDate:'2026-01-25',sourceUrl:'https://example.invalid/nivel'}],page:0,total:1})
    }
    if(path==='/api/v1/release-calendar')return json(fixture(u.searchParams))
    if(path==='/api/v1/auth/refresh')return route.fulfill({status:401,body:'{}'})
    if(path==='/api/v1/auth/admin-mode')return json({mode:'DISABLED'})
    if(path==='/api/v1/packs/9900')return json({id:9901,gameCode:'NIVEL',name:'정정된 수록 상품',total:0,cards:[]})
    if(path.startsWith('/api/v1/packs/')){
      const id=+path.split('/').pop(),event=events.find(e=>e.catalogPackId===id)||catalog.find(p=>p.id===id)
      return json({id,name:event.name,code:event.code,gameCode:event.gameCode,group:'SCHEDULE',metadata:{},total:1,newCount:0,reprintCount:0,newArtCount:0,
        page:0,size:200,hasMore:false,cards:[{id,name:'인쇄 카드',number:'PRINT-001',rarities:[]}]})
    }
    if(path.startsWith('/api/v1/cards/'))return json({id:1,name:'인쇄 카드',gameCode:'POKEMON',specs:{},variants:[]})
    if(path.startsWith('/api/'))return json([])
    const f=extname(path)?path.slice(1):'index.html'
    return route.fulfill({body:await readFile(resolve(dist,f)),contentType:mime[extname(f)]})
  })
  const responseFor=(check)=>page.waitForResponse(r=>{const u=new URL(r.url());return u.pathname==='/api/v1/release-calendar' && !u.searchParams.has('packId') && check(u.searchParams)})
  const game=page.locator('.release-filters select'),region=page.locator('.calendar-heading select')
  const rows=page.locator('.release-month li'), bar=page.locator('.release-views')
  async function check(data){
    await page.locator('.release-summary').waitFor()
    assert.equal(await rows.count(),data.items.length);assert.ok(data.items.length<=24)
    assert.equal(await page.locator('.release-summary time').getAttribute('datetime'),data.asOf)
    assert.deepEqual(await rows.locator('time').evaluateAll(es=>es.map(e=>e.dateTime)),data.items.map(e=>e.releaseDate))
    for(const i of new Set([0,data.items.length-1])){
      if(i<0||!data.items[i])continue
      const e=data.items[i],row=rows.nth(i)
      assert.equal(await row.locator('.event-links a').getAttribute('href'),new URL(e.sourceUrl).href)
      assert.equal(await row.locator('.event-product a').count(),e.catalogPackId?1:0)
      if(e.catalogPackId)assert.equal(new URL(await row.locator('.event-product a').getAttribute('href'),origin).pathname,'/releases/'+e.catalogPackId)
    }
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  }
  let request=responseFor(p=>!p.has('game')&&p.get('period')==='upcoming')
  await page.goto(origin+'/releases?lang=ko')
  let data=await (await request).json();await check(data)
  if(actual){
    const bookmark=origin+'/index.html?lang=ko#pack-DBGV'
    await page.goto(bookmark);await page.locator('.pack-heading h1').filter({hasText:'글로리어스 빅터즈'}).waitFor()
    assert.equal(new URL(page.url()).searchParams.get('lang'),'ko')
    const adjacent=page.locator('.neighbors a.next'),next=new URL(await adjacent.getAttribute('href'),origin)
    await adjacent.click();await page.waitForURL(next.href)
    await page.locator('.neighbors a:not(.next)').click()
    await page.locator('.pack-heading h1').filter({hasText:'글로리어스 빅터즈'}).waitFor()
    if(width===360){
      const el=page.locator('.pack-heading h1')
      await adjacent.waitFor()
      await el.evaluate(target=>{
        const point=(clientX,clientY)=>new Touch({identifier:1,target,clientX,clientY})
        target.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,touches:[point(280,90)]}))
        target.dispatchEvent(new TouchEvent('touchend',{bubbles:true,changedTouches:[point(85,99)]}))
      })
      await page.waitForURL(next.href)
    }
    await page.goto(origin+'/releases?lang=ko')
    const original=page.locator('#release-SCHEDULE li a').filter({hasText:'덱 빌드 팩 글로리어스 빅터즈'})
    await original.waitFor()
    const bounds=await original.boundingBox();assert.ok(bounds.y>=0&&bounds.y+bounds.height<=800,'Original pack must be reachable on the first screen')
    await page.locator('.release-sections a[href="#regional-calendar"]').waitFor()
    await original.click();await page.locator('.pack-row').first().waitFor()
    assert.equal(await page.locator('.pack-row[open]').count(),0)
    assert.match(await page.locator('.pack-heading h1').innerText(),/글로리어스 빅터즈/)
    await page.locator('.pack-back').click();await original.waitFor()
    assert.equal(new URL(page.url()).hash,'#release-SCHEDULE')
    await page.goto(origin+'/releases?game=YUGIOH&q='+encodeURIComponent('글로리어스'))
    await original.waitFor()
    await page.goto(origin+'/releases#release-PREMIERE')
    await page.waitForFunction(()=>{const el=document.querySelector('#release-PREMIERE');return el && Math.abs(el.getBoundingClientRect().top)<180})
    await page.goto(origin+'/releases?lang=ko');await page.locator('.release-summary').waitFor()
  }
  assert.equal(await game.inputValue(),'');assert.deepEqual(await game.locator('option').evaluateAll(os=>os.map(o=>o.value).sort()),['',...codes].sort())
  assert.deepEqual(data.items.map(e=>e.releaseDate),data.items.map(e=>e.releaseDate).sort())
  if(data.total>24){
    request=responseFor(p=>p.get('page')==='1')
    await page.locator('.pagination').getByRole('button',{name:'다음'}).click();await check(await (await request).json())
    assert.equal(await page.locator('.release-summary').evaluate(e=>e===document.activeElement),true)
  }
  request=responseFor(p=>p.get('period')==='past')
  await bar.getByRole('link',{name:'지난 발매'}).click()
  data=await (await request).json();await check(data)
  assert.deepEqual(data.items.map(e=>e.releaseDate),data.items.map(e=>e.releaseDate).sort().reverse())
  request=responseFor(p=>p.get('period')==='all')
  await bar.getByRole('link',{name:'날짜 전체'}).click();await check(await (await request).json())
  const evidence=[]
  for(const code of codes){
    request=responseFor(p=>p.get('game')===code&&p.get('period')==='all')
    await game.selectOption(code)
    data=await (await request).json();await check(data)
    assert.ok(data.total,code+' needs a real schedule entry');assert.ok(data.items.every(e=>e.gameCode===code))
    evidence.push(code+' '+data.total+' '+data.items[0].releaseDate)
  }
  const first=data.items.find(e=>e.catalogPackId)||data.items[0]
  request=responseFor(p=>p.get('game')==='ONEPIECE'&&p.get('region')===first.region)
  await region.selectOption(first.region);data=await (await request).json();await check(data)
  assert.ok(data.items.every(e=>e.region===first.region))
  for(const lang of ['en','ja','ko']){
    await page.locator('.locale-switch select').selectOption(lang)
    const event=data.items[0],label=event.names?.[lang]||event.name||event.code
    await rows.first().getByText(label,{exact:true}).waitFor()
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  }
  const selected=data.items.findIndex(e=>e.catalogPackId)
  if(selected>=0){
    const e=data.items[selected];await rows.nth(selected).locator('.event-product a').click()
    await page.locator('.pack-heading').waitFor()
    if(e.catalogCount>0)await page.locator('.pack-row').first().waitFor()
    await page.locator('.pack-releases time[datetime="'+e.releaseDate+'"]').first().waitFor()
    assert.equal(await page.locator('.pack-releases a[href="'+e.sourceUrl+'"]').count()>0,true)
    await page.locator('.pack-back').click();await page.locator('.release-summary').waitFor()
    assert.equal(new URL(page.url()).hash,'#regional-calendar')
    await page.waitForFunction(()=>{const y=document.querySelector('#regional-calendar').getBoundingClientRect().top;return y>=0 && y<innerHeight})
    assert.equal(await region.inputValue(),first.region);assert.equal(await game.inputValue(),'ONEPIECE')
  }
  request=responseFor(p=>p.get('q')==='no-such-product-qa-0000')
  await page.getByRole('searchbox').fill('no-such-product-qa-0000')
  await check(await (await request).json());await page.getByText('조건에 맞는 발매 일정이 없습니다.').waitFor()
  if(actual){
    request=responseFor(p=>p.get('game')==='YUGIOH'&&p.get('q')==='BETB')
    await page.goto(origin+'/releases?game=YUGIOH&period=past&q=BETB&lang=en')
    data=await (await request).json();await check(data)
    const i=data.items.findIndex(e=>e.code==='BETB'&&e.region==='NA'&&e.catalogPackId&&e.catalogCount>0)
    assert.ok(i>=0,'A verified published Beyond the Brave printing is required in the local QA database')
    const product=data.items[i]
    const res=await ctx.request.get(origin+'/api/v1/packs/'+product.catalogPackId+'?lang=en&page=0&size=1')
    assert.equal(res.status(),200);const details=await res.json()
    await rows.nth(i).locator('.event-product a').click()
    await page.locator('.pack-row').first().getByText(details.cards[0].number,{exact:true}).waitFor()
    assert.equal(await page.locator('.pack-row[open]').count(),0)
    assert.equal(details.total,product.catalogCount)
    assert.equal(await page.getByRole('link',{name:'Official product page'}).getAttribute('href'),product.sourceUrl)
    assert.ok((await page.locator('.pack-dates').innerText()).includes(product.releaseDate))
    if(process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,'released-pack-'+width+'.png')})}
    await page.locator('.pack-back').click();await page.locator('.release-summary').waitFor()
    assert.equal(await page.getByRole('searchbox').inputValue(),'BETB')
    assert.equal(new URL(page.url()).searchParams.get('period'),'past')
  }
  await page.goto(origin+'/releases?lang=ko')
  await page.locator('.release-summary').waitFor()
  if(process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,'release-calendar-'+width+'.png')})}
  if(!actual){
    await page.getByRole('button',{name:'월간 달력'}).click()
    await page.locator('.month-picker').waitFor()
    await page.locator('.release-multi summary').click()
    for(const name of ['유희왕','포켓몬 TCG','북미','영어판','부스터 팩'])
      await page.locator('.release-multi').getByLabel(name,{exact:true}).check()
    await page.waitForURL(u=>u.searchParams.get('productType')==='BOOSTER')
    await page.locator('.release-summary').waitFor()
    const multiple=new URL(page.url()).searchParams
    assert.deepEqual(multiple.get('game').split(',').sort(),['POKEMON','YUGIOH'])
    assert.deepEqual(multiple.get('region').split(',').sort(),['EN','NA'])
    const active=page.locator('.date-grid button').first();await active.waitFor()
    const iso=(await active.getAttribute('aria-label')).slice(0,10);await active.click()
    await page.waitForURL(u=>u.searchParams.get('day')===iso)
    assert.ok((await rows.locator('time').evaluateAll(items=>items.map(x=>x.dateTime))).every(d=>d===iso))
    assert.match(await rows.first().locator('time small').innerText(),/^D(?:−|\+|-Day)/)
    await page.getByRole('button',{name:'이 달의 전체 일정'}).click()
    await page.getByRole('button',{name:'다음 달'}).click()
    await page.waitForURL(u=>u.searchParams.get('month')==='2026-12')
    await page.getByRole('button',{name:'타임라인'}).click()
    await page.waitForURL(u=>!u.searchParams.has('view') && u.searchParams.get('game')?.includes(','))
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  }
  if(!actual){
    await page.goto(origin+'/releases/9900?lang=ko')
    const calendar=page.locator('.pack-releases')
    await calendar.getByRole('heading',{name:'지역별 발매 일정'}).waitFor()
    assert.equal(await calendar.locator('time').getAttribute('datetime'),'2026-01-25')
    assert.equal(await calendar.getByRole('link').getAttribute('href'),'https://example.invalid/nivel')
  }
  for(const gameCode of codes){
    const product=actual
      ? (await (await ctx.request.get(origin+'/api/v1/catalog-packs?game='+gameCode+'&size=1')).json()).items[0]
      : catalog.find(p=>p.gameCode===gameCode)
    assert.ok(product,gameCode+' needs a catalogued pack')
    const term=product.code||product.name
    await page.goto(origin+'/releases?lang=ko&game='+gameCode)
    await page.getByRole('searchbox').fill(term)
    const finder=page.locator('#catalog-packs')
    const link=finder.locator('a[href^="/releases/'+product.id+'?"]')
    await link.waitFor()
    assert.match(await link.innerText(),new RegExp(product.catalogCount.toLocaleString('ko')))
    if(!actual)await page.getByText('조건에 맞는 발매 일정이 없습니다.').waitFor()
    if(gameCode==='ONEPIECE' && process.env.QA_SCREENSHOTS)await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,'pack-search-'+width+'.png')})
    await link.click();await page.locator('.pack-heading h1').waitFor()
    await page.locator('.pack-back').click();await link.waitFor()
    assert.equal(await page.getByRole('searchbox').inputValue(),term)
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  }
  if(!actual){
    await page.goto(origin+'/releases?browse=1&packQuery=OP-01&packGame=ONEPIECE#catalog-packs')
    await page.locator('#catalog-packs a').filter({hasText:'ROMANCE DAWN'}).waitFor()
    assert.equal(await page.getByRole('searchbox').inputValue(),'OP-01')
    await page.getByRole('searchbox').fill('')
    await game.selectOption('RIFTBOUND')
    await page.locator('#catalog-packs a').filter({hasText:'Origins'}).waitFor()
    await page.goto(origin+'/releases?game=YUGIOH,ONEPIECE&q=OP-01')
    await page.locator('#catalog-packs select').selectOption('ONEPIECE')
    await page.locator('#catalog-packs a').filter({hasText:'ROMANCE DAWN'}).waitFor()
    await page.goto(origin+'/releases?game=POKEMON&q=QA-SERIES')
    const sets=page.locator('#catalog-packs')
    await sets.getByRole('button',{name:/수록 팩 찾기/}).click()
    await sets.locator('.pagination').getByRole('button',{name:'다음'}).click()
    await sets.getByRole('link').filter({hasText:'QA-SERIES-26'}).waitFor()
    assert.equal(await sets.getByRole('link').count(),2)
    await page.getByRole('searchbox').fill('SV1V')
    await sets.getByRole('link').filter({hasText:'바이올렛 ex'}).waitFor()
    assert.equal(new URL(page.url()).searchParams.has('packPage'),false)
  }
  assert.deepEqual(errors,[]);console.log(width+'px '+(actual?'Spring':'fixture')+' six games, default, periods, paging, region, locale, source/pack links, search and width passed: '+evidence.join(' / '))
  await ctx.close()
 }
}finally{await browser.close()}
