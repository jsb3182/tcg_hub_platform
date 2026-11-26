// Run after npm run build. Uses in-memory contract fixtures and the installed Chromium.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile} from 'node:fs/promises'
import {extname,join} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
const dist=fileURLToPath(new URL('../dist/',import.meta.url)), origin='http://127.0.0.1:19891'
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png'}
const codes=['YUGIOH','POKEMON','ONEPIECE','WEISS','NIVEL','RIFTBOUND']
const titles={ko:'연습용 카드',en:'Practice card',ja:'練習カード'}, writes=[],errors=[]
const deck={id:70,name:'Fixture deck',gameCode:'ONEPIECE',revision:1,state:'DRAFT',updatedAt:'2026-11-01T00:00:00Z',entries:[],rule:{version:1,sections:[{section:'MAIN',minCards:50,maxCards:50}]}}
try {
 const context=await browser.newContext({viewport:{width:360,height:800},isMobile:true,hasTouch:true,serviceWorkers:'block'})
 // Android System WebView 91 predates these built-ins. Disable them before any app module loads.
 await context.addInitScript(()=>{
   delete Object.hasOwn
   delete Array.prototype.at
   delete Array.prototype.toSorted
   delete Array.prototype.toReversed
   delete Array.prototype.toSpliced
   delete globalThis.structuredClone
   if (window.Crypto) delete Crypto.prototype.randomUUID
 })
 const page=await context.newPage()
 page.setDefaultTimeout(4500)
 page.on('pageerror',e=>errors.push(e.message))
 await context.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url()),path=u.pathname
  if(u.origin!==origin)return route.abort()
  const json=(data,status=200)=>route.fulfill({json:data,status})
  if(path.startsWith('/api/')){
   const api=path.replace(/^\/api\/(v1\/)?/,''), lang=u.searchParams.get('lang')||'ko'
   const card={id:51,name:titles[lang],language:lang,gameCode:u.searchParams.get('game')||'ONEPIECE',number:'QA-51',rarity:'R',effect:'Fixture effect',effectLanguage:'en'}
   if(req.method()!=='GET'&&api!=='auth/refresh'){
     assert.equal(req.headers()['x-tcg-request'],'1');assert.equal(req.headers().authorization,'Bearer fixture')
     const body=req.postData()?req.postDataJSON():null
     writes.push({api,query:Object.fromEntries(u.searchParams),body})
   }
   if(api==='auth/refresh')return json({accessToken:'fixture',email:'operator@example.invalid',role:'ROLE_ADMIN'})
   if(api==='auth/admin-mode')return json({mode:'CLOUDFLARE'})
   if(api==='games')return json(codes.map(code=>({code,name:code})))
   if(api==='packs')return json([])
   if(api==='config')return json({kakaoMapKey:''})
   if(api==='stores')return json({items:[{id:8,name:'Fixture shop',address:'Seoul',lat:37.5,lon:127,games:[{code:'ONEPIECE'}],official:true,events:[{id:5,title:'Store tournament',gameCode:'ONEPIECE',startsAt:'2026-11-25T10:00:00Z'}]}],total:1})
   if(api==='me/favorites/stores')return json([])
   if(api==='play/cards')return json([card])
   if(api==='cards')return json({items:[card],total:1})
   if(api==='cards/51')return json({...card,variants:[],specs:{names:titles}})
   if(api==='me/binder/stats')return json(codes.map(gameCode=>({gameCode,copies:0,uniqueCards:0})))
   if(api==='me/binder')return json({items:[{cardId:51,name:card.name,edition:'en',condition:'NM',tradable:true,quantity:2}],total:1,copies:2})
   if(api==='me/binder/51')return json({quantity:u.searchParams.get('edition')==='ja'?3:2})
   if(api==='me/decks')return json({items:[],total:0})
   if(api==='me/decks/import')return json(deck,201)
   if(api==='me/decks/70')return json(deck)
   if(api==='me/decks/70/code')return json({code:'TCGHUB1-fixture'})
   if(api==='admin/operations')return json({cardCounts:{ONEPIECE:1},sources:[]})
   if(api==='admin/server/status')return json({database:'UP',schedulerEnabled:true,crawlerEnabled:true,hostControlAvailable:false})
   if(api==='admin/actions')return json([{action:'TEST_ACTION',occurredAt:'2026-11-01T00:00:00Z'}])
   if(api==='admin/users')return json([{id:8,email:'fixture@example.invalid',role:'ROLE_USER',enabled:true}])
   if(api==='admin/posts')return json({items:[{id:4,title:'Fixture post',hidden:false,pinned:false}],total:1})
   if(api==='admin/stores')return json([{id:8,name:'Fixture shop',address:'Seoul',gameCodes:['ONEPIECE'],version:2}])
   if(api==='news')return json({items:[{id:3,title:titles[lang],originalTitle:'Practice card',originalLanguage:'en',originalSummary:'Original summary',summary:'Original summary',contentLanguage:lang,summaryLanguage:'en',translationStatus:lang==='en'?'ORIGINAL':'TRANSLATED',gameCode:'ONEPIECE',sourceUrl:'https://example.invalid/news/3'}],total:1})
   errors.push('Unknown route '+api);return json({},404)
  }
  const file=(path.startsWith('/assets/')||extname(path))?path.slice(1):'index.html'
  try{return await route.fulfill({contentType:mime[extname(file)],body:await readFile(join(dist,file))})}catch{return route.fulfill({status:404,body:''})}
 })
 const go=p=>page.goto(origin+p),btn=n=>page.getByRole('button',{name:n,exact:true})
 const select=page.locator('.locale-switch select')
 const visible=e=>e.waitFor({state:'visible'})
 const fits=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),360)
 await go('/cards/51?lang=ja')
 await visible(page.getByRole('heading',{name:'練習カード'}))
 await visible(page.locator('.card-facts [lang=en]').filter({hasText:'Practice card'}))
 assert.equal(await page.locator('html').getAttribute('lang'),'ja')
 assert.equal(await select.inputValue(),'ja')
 await go('/'); await visible(page.locator('.catalog-games button').last());assert.equal(await page.locator('.catalog-games button').count(),7)
 await select.selectOption('en');await visible(page.getByRole('heading',{name:'Card catalog',exact:true}))
 await go('/news?game=ONEPIECE&lang=ja');await visible(page.getByRole('heading',{name:'練習カード'}));assert.equal(await page.locator('.story-summary').getAttribute('lang'),'en')
 await page.locator('.story-original summary').click();await visible(page.locator('.story-original strong'));await fits()
 await go('/play?game=ONEPIECE&lang=en');assert.equal(await page.locator('.practice-setup input[type=number]').inputValue(),'5')
 for(let i=0;i<8;i++)await btn('Add Practice card').click()
 await btn('Shuffle and start').click();const zones=page.locator('.practice-zones>section')
 await visible(zones.nth(0).getByRole('heading',{name:'Hand · 5'}))
 await zones.nth(0).getByRole('checkbox').first().check()
 await btn('Redraw selected cards (1)').click();await btn('Draw one').click()
 await zones.nth(0).getByRole('button',{name:'Place on table'}).first().click()
 const resources=page.locator('.resource-controls')
 await resources.getByRole('spinbutton').fill('2');await resources.getByRole('button',{name:'Add',exact:true}).click()
 await zones.nth(1).getByRole('button',{name:'Attach'}).click()
 await resources.getByRole('spinbutton').fill('1');await resources.getByRole('button',{name:'Pay cost'}).click()
 await visible(resources.getByRole('heading',{name:'DON!! · 0'}))
 await select.selectOption('ja');await visible(zones.nth(1).getByRole('heading',{name:'テーブル · 1'}));await fits()
 await go('/binder');await select.selectOption('en');await visible(page.locator('.binder-pockets li'))
 await page.locator('.binder-pockets button').click()
 const dialog=page.getByRole('dialog')
 const lotRead=page.waitForResponse(r=>r.url().includes('edition=ja'));await dialog.locator('select').nth(0).selectOption('ja');await lotRead
 await dialog.getByRole('spinbutton').fill('4');await dialog.locator('button.primary').click()
 await page.waitForFunction(()=>!document.querySelector('dialog[open]'))
 const lot=writes.find(x=>x.api==='me/binder/51');assert.deepEqual(lot.body,{expectedQuantity:3,quantity:4});assert.deepEqual(lot.query,{edition:'ja',condition:'NM',tradable:'true'})
 await page.locator('.view-control button').last().click();assert.equal(await page.locator('.binder-pockets').count(),0);await fits()
 await go('/decks');await page.locator('.deck-code summary').click();await page.locator('.deck-code textarea').fill('TCGHUB1-fixture');await page.locator('.deck-code button').click()
 await page.waitForURL('**/decks/70**');await page.locator('.deck-code summary').click();await page.locator('.deck-code button').click();assert.equal(await page.locator('.deck-code textarea').inputValue(),'TCGHUB1-fixture')
 await go('/stores');await page.locator('.store-select').click();await visible(page.getByText('Store tournament',{exact:false}));await visible(page.locator('.ol-viewport'));await fits()
 await go('/admin');await btn('Server controls').click();await visible(page.getByText('TEST_ACTION'));assert.equal(await btn('Shut down server').isDisabled(),true)
 await btn('Member roles').click();await visible(page.getByText('fixture@example.invalid'))
 await btn('Posts').click();await visible(page.getByText('Fixture post'))
 await btn('Stores').click();await visible(page.getByText('Fixture shop'))
 await select.selectOption('ja');await visible(btn('店舗を登録'));await fits()
 assert.deepEqual(errors,[])
 console.log('360px Chrome passed: six-game catalog; trilingual navigation and original news; One Piece redraw, draw, field and DON!!; differentiated binder writes; deck-code import/export; OSM store/event selection; four admin tools and disabled host actions.')
}finally{await browser.close()}
