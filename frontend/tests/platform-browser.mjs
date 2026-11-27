// Run after npm run build. Uses in-memory contract fixtures and the installed Chromium.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,join} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
const dist=fileURLToPath(new URL('../dist/',import.meta.url)), origin='http://127.0.0.1:19891'
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png'}
const subscriptions=[]
let fixtureRole='ROLE_ADMIN'
const codes=['YUGIOH','POKEMON','ONEPIECE','WEISS','NIVEL','RIFTBOUND']
const titles={ko:'연습용 카드',en:'Practice card',ja:'練習カード'}, writes=[],errors=[]
const effects={ko:'확인된 한국어 효과',en:'Verified English effect',ja:'確認済みの日本語効果'}
const atlasTile=(col,language)=>({sheetId:9,col,row:0,url:'/media/fixture.webp',cellWidth:200,cellHeight:290,language})
const atlasVariants=[{id:71,image:atlasTile(0,'en')},{id:72,image:atlasTile(3,'ja')},{id:73,image:atlasTile(2,null)}]
function atlasCard(lang){
 return {id:54,name:titles[lang],language:lang,effect:effects[lang],effectLanguage:lang,gameCode:'YUGIOH',number:'AT-54',
   nameBasis:'PRINTED_NAME',nameReferenceUrl:'https://example.invalid/prints/'+lang+'/name',
   effectReferenceUrl:'https://example.invalid/prints/'+lang+'/effect',
   imageUrl:null,imageLanguage:null,image:(atlasVariants.find(v=>v.image.language===lang)||atlasVariants[0]).image}
}
function artwork(id,lang){
 const productCode='EB01'
 const imageLanguage=lang==='ja'?'ko':lang
 const imageProduct=id===51?'OP-14':id===52?productCode:null
 const imageSource=imageProduct?'https://example.invalid/prints/'+imageLanguage+'/'+imageProduct:null
 return {productCode,imageUrl:'/media/fixture.webp',imageLanguage,imageProduct,imageSource}
}
const deck={id:70,name:'Fixture deck',gameCode:'ONEPIECE',revision:1,state:'DRAFT',updatedAt:'2026-11-01T00:00:00Z',entries:[],rule:{version:1,sections:[{section:'MAIN',minCards:50,maxCards:50}]}}
const sourceCard={id:54,name:'수집 카드 QA',number:'QA-54',gameCode:'YUGIOH',status:'PENDING',version:1,editable:false,specs:{}}
let translation={lang:'ja',name:'保存済み',effect:'',sourceUrl:'https://example.invalid/ja',basis:'TRANSLATED_NAME',version:1},firstSave=true
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
  if(u.origin==='https://example.invalid' && path.startsWith('/prints/') && req.isNavigationRequest())
    return route.fulfill({contentType:'text/plain',body:'Fixture card printing'})
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
   if(api==='auth/refresh')return json({accessToken:'fixture',email:'operator@example.invalid',role:fixtureRole})
   if(api==='auth/admin-mode')return json({mode:'CLOUDFLARE'})
   if(api==='games')return json(codes.map(code=>({code,name:code})))
   if(api==='packs')return json([])
   if(api==='config')return json({kakaoMapKey:''})
   if(api==='stores')return json({items:[{id:8,name:'Fixture shop',address:'Seoul',lat:37.5,lon:127,games:[{code:'ONEPIECE'}],official:true,events:[
     {id:5,category:'TOURNAMENT',title:'Store championship',gameCode:'ONEPIECE',startsAt:'2026-11-25T10:00:00Z',sourceUrl:'https://example.invalid/official-store-event'},
     {id:6,category:'RESTOCK',title:'신상품 입고',gameCode:null,startsAt:'2026-11-25T13:30:00Z',sourceUrl:'https://example.invalid/store-restock'}
   ]}],total:1})
   if(api==='me/favorites/stores')return json([])
   if(api==='play/cards' && u.searchParams.get('game')==='YUGIOH')return json([atlasCard(lang)])
   if(api==='play/cards')return json([{...card,...artwork(51,lang)}])
   if(api==='cards' && u.searchParams.get('game')==='YUGIOH')return json({items:[atlasCard(lang)],total:1})
   if(api==='cards')return json({items:[card],total:1})
   if(api==='cards/54')return json({...atlasCard(lang),specs:{},variants:atlasVariants})
   if(api==='cards/55')return json({...atlasCard(lang),id:55,imageUrl:'/media/fixture.webp',imageLanguage:'en',specs:{},variants:atlasVariants})
   if(api==='cards/56')return json({...atlasCard(lang),id:56,imageUrl:'/media/fixture.webp',imageLanguage:lang,imageBasis:'CARD_REFERENCE',imageSource:'https://example.invalid/prints/'+lang+'/art',effectBasis:lang==='ko'?'REVIEWED_TRANSLATION':'REVIEWED_PRINTING',specs:{names:{[lang]:'Obsolete unreviewed name'}},variants:atlasVariants})
   if(['cards/51','cards/52','cards/53'].includes(api)){
     const id=Number(api.split('/')[1])
     return json({...card,id,...artwork(id,lang),effectBasis:'RELATED_PRINTING',variants:[],specs:{names:titles,sources:{ja:'https://example.invalid/public-card-ja'}}})
   }
   if(api.startsWith('shared/decks/')){
     const gameCode=api.split('/').pop()
     assert.ok(codes.includes(gameCode))
     const entries=[{name:'First card',cardId:10,quantity:3,curveValue:0},{name:'Second card',cardId:11,quantity:3,curveValue:4},{name:'Unknown value',cardId:12,quantity:2,curveValue:null}].map(e=>({...e,section:'MAIN'}))
     return json({...deck,gameCode,entries:[...entries,{name:'Excluded card',cardId:73,section:'SIDE',quantity:15,curveValue:9}]})
   }
   if(api==='me/binder/stats')return json(codes.map(gameCode=>({gameCode,copies:0,uniqueCards:0})))
   if(api==='me/binder')return json({items:[{cardId:51,...card,name:lang==='ja'?'Practice card':card.name,language:lang==='ja'?'en':lang,nameBasis:lang==='ko'?'TRANSLATED_NAME':'SOURCE_LABEL',edition:'en',condition:'NM',tradable:true,quantity:2}],total:1,copies:2})
   if(api==='me/binder/51')return json({quantity:u.searchParams.get('edition')==='ja'?3:2})
   if(api==='me/decks')return json({items:[],total:0})
   if(api==='me/decks/import')return json(deck,201)
   if(api==='me/decks/70')return json(deck)
   if(api==='me/decks/71')return json({...deck,id:71,gameCode:'YUGIOH',nameJa:'保存済み',nameEn:'Saved deck',
     entries:[{...atlasCard(lang),cardId:54,section:'MAIN',quantity:2,variantId:72,image:atlasTile(3,'ja')}]})
   if(api==='me/decks/rules/YUGIOH')return json({...deck.rule,sections:[{section:'MAIN',minCards:40,maxCards:60}]})
   if(api==='me/decks/needed')return json({items:[{cardId:54,name:titles.en,language:'en',nameBasis:'SOURCE_LABEL',number:'AT-54',owned:0,required:1}],next:null})
   if(api==='me/decks/70/code')return json({code:'TCGHUB1-fixture'})
   if(api==='admin/operations')return json({cardCounts:{ONEPIECE:1},sources:subscriptions})
   if(api==='admin/catalog/cards')return json({items:[sourceCard],total:1})
   if(api==='admin/catalog/cards/54')return json(sourceCard)
   if(api==='admin/catalog/cards/54/translations')return json([translation])
   if(api==='admin/catalog/cards/54/translations/ja'){
     if(firstSave){firstSave=false;translation={...translation,name:'別の編集',version:2};return json({},409)}
     const edit=req.postDataJSON();assert.equal(edit.version,translation.version)
     translation={...edit,lang:'ja',version:edit.version+1};return json(translation)
   }
   if(api==='admin/sources/x'){
     const {username,gameCode,storeId}=req.postDataJSON()
     if(username==='invalid_store')return json({},400)
     if(subscriptions.some(source=>source.name==='@'+username))return json({},409)
     subscriptions.push({id:90+subscriptions.length,name:'@'+username,enabled:true,provider:'X',state:'IDLE',gameCode,storeId,intervalSeconds:7200})
     return json({id:subscriptions[subscriptions.length-1].id},201)
   }
   if(api==='admin/server/status')return json({database:'UP',schedulerEnabled:true,crawlerEnabled:true,hostControlAvailable:false})
   if(api==='admin/actions')return json([{action:'TEST_ACTION',occurredAt:'2026-11-01T00:00:00Z'}])
   if(api==='admin/users')return json([{id:8,email:'fixture@example.invalid',role:'ROLE_USER',enabled:true}])
   if(api==='admin/posts')return json({items:[{id:4,title:'Fixture post',hidden:false,pinned:false}],total:1})
   if(api==='admin/stores' && u.searchParams.get('q')==='not-a-store')return json([])
   if(api==='admin/stores')return json([{id:8,name:'Fixture shop',address:'Seoul',gameCodes:['ONEPIECE'],version:2}])
   if(api==='news')return json({items:[{id:3,title:titles[lang],originalTitle:'Practice card',originalLanguage:'en',originalSummary:'Original summary',summary:'Original summary',contentLanguage:lang,summaryLanguage:'en',translationStatus:lang==='en'?'ORIGINAL':'TRANSLATED',gameCode:'ONEPIECE',sourceUrl:'https://example.invalid/news/3'}],total:1})
   errors.push('Unknown route '+api);return json({},404)
  }
  if(path==='/media/fixture.webp')return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2ZkAAAAASUVORK5CYII=','base64')})
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
 assert.equal(await page.locator('.card-facts [lang=ja] a').getAttribute('href'),'https://example.invalid/public-card-ja')
 await visible(page.locator('.detail-section .card-text-credit').filter({hasText:'効果の言語 · 英語'}))
 await visible(page.locator('.detail-section .card-text-credit').getByText('別の収録版を参考にした効果',{exact:true}))
 const translations={
   ko:{different:'다른 제품의 그림',same:'그림 수록 제품',unknown:'수록 제품 미확인',edition:'한국어판'},
   en:{different:'Art from another set',same:'Art from set',unknown:'Printing unconfirmed',edition:'English edition'},
   ja:{different:'別商品のカード画像',same:'画像の収録商品',unknown:'収録商品未確認',edition:'韓国語版'},
 }
 async function checkCredit(credit,lang,kind){
   const copy=translations[lang],code=kind==='different'?'OP-14':'EB01'
   await visible(credit.getByText(copy.edition,{exact:true}))
   const link=credit.getByRole('link')
   if(kind==='unknown'){
     await visible(credit.getByText(copy.unknown,{exact:true}))
     assert.equal(await link.count(),0)
   }else{
     await visible(credit.getByRole('link',{name:copy[kind]+' · '+code,exact:true}))
     assert.equal(await link.getAttribute('href'),'https://example.invalid/prints/'+(lang==='ja'?'ko':lang)+'/'+code)
     assert.equal(await link.getAttribute('target'),'_blank')
     assert.ok((await link.getAttribute('rel')).split(/\s+/).includes('noopener'))
   }
 }
 async function openCredit(credit,expected){
   const [tab]=await Promise.all([page.waitForEvent('popup'),credit.getByRole('link').click()])
   try{
     await tab.waitForURL(expected)
     await visible(tab.getByText('Fixture card printing',{exact:true}))
   }finally{await tab.close()}
 }
 for(const [id,kind] of [[51,'different'],[52,'same'],[53,'unknown']]){
   await go('/cards/'+id+'?lang=ko')
   for(const lang of ['ko','en','ja']){
     await select.selectOption(lang)
     await checkCredit(page.locator('.illustration .edition-note'),lang,kind)
     await fits()
     if(id===51 && lang==='ja'){
       await openCredit(page.locator('.illustration .edition-note'),'https://example.invalid/prints/ko/OP-14')
       if(process.env.QA_SCREENSHOTS){
         await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
         await page.locator('.detail-grid').screenshot({path:join(process.env.QA_SCREENSHOTS,'artwork-credit-detail-360.png')})
       }
     }
   }
 }
 // This synthetic printing has two verified atlas languages and one unverified tile.
 await go('/?game=YUGIOH&lang=ja')
 const preview=page.locator('.card-row summary .lib-thumbnail')
 const position=async (art,expected)=>assert.equal(await art.evaluate(e=>getComputedStyle(e).backgroundPosition),expected)
 await visible(preview);await position(preview,'100% 0%')
 await page.locator('.card-row summary').click()
 const caption=page.locator('.illustration .edition-note')
 await visible(caption.getByText('日本語版',{exact:true}))
 await position(page.locator('.illustration button.atlas'),'100% 0%')
 await page.locator('.variant-nav button').last().click()
 await visible(caption.getByText('言語未確認',{exact:true}))
 await page.locator('.illustration button.atlas').click()
 await position(page.getByRole('dialog').locator('.atlas'),'66.6667% 0%')
 await page.getByRole('dialog').getByRole('button').click()
 await go('/cards/54?lang=ko')
 await visible(caption.getByText('영어판',{exact:true}))
 assert.match(await caption.innerText(),/대체 이미지/)
 await position(page.locator('.illustration button.atlas'),'0% 0%')
 await visible(page.locator('.detail-section p[lang=ko]').getByText(effects.ko))
 // When a direct image is also available, a matching atlas beats a different-language URL.
 await go('/cards/55?lang=ja');await visible(caption.getByText('日本語版',{exact:true}))
 await position(page.locator('.illustration button.atlas'),'100% 0%')
 await select.selectOption('en');await visible(page.locator('.illustration .localized-card img'))
 await visible(caption.getByText('English edition',{exact:true}))
 // A general reference has its own citation. A matching, verified local printing wins a tie.
 await go('/cards/56?lang=ko')
 await visible(caption.getByRole('link',{name:'카드 참고 이미지'}))
 assert.equal(await caption.locator('a').getAttribute('href'),'https://example.invalid/prints/ko/art')
 await select.selectOption('ja')
 await visible(caption.getByText('日本語版',{exact:true}))
 assert.equal(await caption.locator('a').count(),0)
 for(const lang of ['ko','en','ja']){
   await select.selectOption(lang)
   await visible(page.locator('.card-facts .card-text-credit a[href$="/'+lang+'/name"]'))
   await visible(page.locator('.detail-section .card-text-credit a[href$="/'+lang+'/effect"]'))
   await visible(page.locator('.detail-section .card-text-credit').getByText(({ko:'검수한 번역 효과',en:'Verified printed effect',ja:'確認済みの収録版の効果'})[lang],{exact:true}))
   assert.equal(await page.getByText('Obsolete unreviewed name',{exact:true}).count(),0)
   await fits()
 }
 await go('/?game=YUGIOH&lang=ko')
 await visible(page.locator('.catalog-edition').filter({hasText:'대체 이미지 · 영어판'}))
 await go('/play?game=YUGIOH&lang=ja')
 await btn('追加 練習カード').click();await page.locator('.practice-setup button.primary').click()
 const hand=page.locator('.practice-zones>section').first()
 for(const [lang,edition,positionValue] of [['ja','日本語版','100% 0%'],['en','English edition','0% 0%'],['ko','영어판','0% 0%']]){
   await select.selectOption(lang)
   await visible(hand.locator('strong[lang='+lang+']').getByText(titles[lang]))
   await visible(hand.locator('figcaption').getByText(edition,{exact:true}))
   await position(hand.locator('.lib-thumbnail'),positionValue)
   assert.equal((await hand.locator('figcaption').innerText()).includes('대체 이미지'),lang==='ko')
   const detail=hand.locator('details')
   if(!await detail.evaluate(e=>e.open))await detail.locator('summary').click()
   await visible(detail.locator('p[lang='+lang+']').getByText(effects[lang]))
   await visible(detail.locator('a[href$="/'+lang+'/effect"]'))
   await visible(hand.locator('a[href$="/'+lang+'/name"]'))
   await fits()
 }
 for(const [game,size] of Object.entries({YUGIOH:5,POKEMON:7,ONEPIECE:5,WEISS:5,NIVEL:5,RIFTBOUND:4})){
   await go('/shared/decks/'+game+'?lang=en')
   await visible(page.getByRole('heading',{name:'Deck curve',exact:true}))
   const opening=page.locator('.opening-panel')
   assert.equal(await opening.getByRole('spinbutton').inputValue(),String(size))
   assert.equal(await page.locator('.curve-list li').count(),2)
   assert.match(await page.locator('.curve-list li').first().innerText(),/0\s+3/)
   await visible(page.locator('.curve-panel').getByText(/No recorded value.*2/))
   await opening.getByRole('button').click()
   assert.equal(await opening.locator('ol li').count(),size)
   assert.ok(!(await opening.innerText()).includes('Excluded card'))
   await opening.getByRole('spinbutton').fill('10')
   await opening.getByRole('button').click()
   assert.equal(await opening.locator('ol li').count(),8)
   await fits()
   if(game==='ONEPIECE' && process.env.QA_SCREENSHOTS) {
     await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
     await page.locator('.deck-analysis').screenshot({path:join(process.env.QA_SCREENSHOTS,'deck-analysis-360.png')})
   }
 }
 await go('/'); await visible(page.locator('.catalog-games button').last());assert.equal(await page.locator('.catalog-games button').count(),7)
 await select.selectOption('en');await visible(page.getByRole('heading',{name:'Card catalog',exact:true}))
 await go('/news?game=ONEPIECE&lang=ja');await visible(page.getByRole('heading',{name:'練習カード'}));assert.equal(await page.locator('.story-summary').getAttribute('lang'),'en')
 await page.locator('.story-original summary').click();await visible(page.locator('.story-original strong'));await fits()
 await go('/play?game=ONEPIECE&lang=en');assert.equal(await page.locator('.practice-setup input[type=number]').inputValue(),'5')
 for(let i=0;i<8;i++)await btn('Add Practice card').click()
 await btn('Shuffle and start').click();const zones=page.locator('.practice-zones>section')
 await visible(zones.nth(0).getByRole('heading',{name:'Hand · 5'}))
 await visible(zones.nth(0).locator('figcaption').first())
 for(const caption of await zones.nth(0).locator('figcaption').all())await checkCredit(caption,'en','different')
 assert.equal(await zones.nth(0).locator('figcaption a').count(),5)
 await zones.nth(0).getByRole('checkbox').first().check()
 await btn('Redraw selected cards (1)').click();await btn('Draw one').click()
 await zones.nth(0).getByRole('button',{name:'Place on table'}).first().click()
 const resources=page.locator('.resource-controls')
 await resources.getByRole('spinbutton').fill('2');await resources.getByRole('button',{name:'Add',exact:true}).click()
 await zones.nth(1).getByRole('button',{name:'Attach'}).click()
 await resources.getByRole('spinbutton').fill('1');await resources.getByRole('button',{name:'Pay cost'}).click()
 await visible(resources.getByRole('heading',{name:'DON!! · 0'}))
 for(const lang of ['ko','ja']){
   await select.selectOption(lang)
   await checkCredit(zones.nth(1).locator('figcaption'),lang,'different')
   assert.equal(await zones.nth(0).locator('figcaption a').count(),5)
   await fits()
 }
 await visible(zones.nth(1).getByRole('heading',{name:'テーブル · 1'}))
 await openCredit(zones.nth(1).locator('figcaption'),'https://example.invalid/prints/ko/OP-14')
 if(process.env.QA_SCREENSHOTS){
   await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
   await zones.nth(1).screenshot({path:join(process.env.QA_SCREENSHOTS,'artwork-credit-practice-360.png')})
 }
 await zones.nth(1).getByRole('button',{name:'手札に戻す'}).click()
 await visible(zones.nth(0).getByRole('heading',{name:'手札 · 6'}))
 await go('/binder');await select.selectOption('en');await visible(page.locator('.binder-pockets li'))
 const owned=page.locator('.binder-pockets li').first()
 for(const [l,actual,label,credit] of [['ko','ko',titles.ko,'번역 카드명'],['ja','en',titles.en,'カード名の言語 · 英語'],['en','en',titles.en,'Source catalog name']]){
   await select.selectOption(l)
   await visible(owned.locator('a[lang='+actual+']').getByText(label,{exact:true}))
   await visible(owned.locator('.card-text-credit').filter({hasText:credit}))
   assert.equal(new URL(await owned.locator('a').first().getAttribute('href'),origin).searchParams.get('lang'),l)
   await fits()
 }
 await page.locator('.binder-pockets button').click()
 const dialog=page.getByRole('dialog')
 const lotRead=page.waitForResponse(r=>r.url().includes('edition=ja'));await dialog.locator('select').nth(0).selectOption('ja');await lotRead
 await dialog.getByRole('spinbutton').fill('4');await dialog.locator('button.primary').click()
 await page.waitForFunction(()=>!document.querySelector('dialog[open]'))
 const lot=writes.find(x=>x.api==='me/binder/51');assert.deepEqual(lot.body,{expectedQuantity:3,quantity:4});assert.deepEqual(lot.query,{edition:'ja',condition:'NM',tradable:'true'})
 await page.locator('.view-control button').last().click();assert.equal(await page.locator('.binder-pockets').count(),0);await fits()
 await go('/decks');await page.locator('.deck-code summary').click();await page.locator('.deck-code textarea').fill('TCGHUB1-fixture');await page.locator('.deck-code button').click()
 await page.waitForURL('**/decks/70**');await page.locator('.deck-code summary').click();await page.locator('.deck-code button').click();assert.equal(await page.locator('.deck-code textarea').inputValue(),'TCGHUB1-fixture')
 // A new deck must relabel its real cards before it has a server-side deck ID.
 await go('/decks/new?game=YUGIOH&lang=ko')
 await page.getByRole('button',{name:titles.ko+' 추가',exact:true}).click()
 await page.locator('.lib-controls input').fill('2')
 for(const lang of ['en','ja','ko']){
   await select.selectOption(lang)
   await visible(page.locator('.lib-list strong[lang='+lang+']').getByText(titles[lang],{exact:true}).first())
   await visible(page.locator('.lib-recipe span[lang='+lang+']').getByText(titles[lang],{exact:true}))
   assert.equal(await page.locator('.lib-controls input').inputValue(),'2')
   assert.ok(new URL(page.url()).pathname.endsWith('/new'))
   await fits()
 }
 page.once('dialog',d=>d.accept())
 await go('/decks/71?lang=ja')
 const lines=page.locator('.recipe-panel .lib-recipe ul').first()
 await visible(lines.getByText(titles.ja,{exact:true}))
 await page.locator('.lib-controls input').fill('3')
 for(const lang of ['en','ko','ja']){
   await select.selectOption(lang)
   await visible(lines.locator('[lang='+lang+']').getByText(titles[lang],{exact:true}))
   await position(lines.locator('.lib-thumbnail'),'100% 0%')
   assert.equal(await page.locator('.lib-controls input').inputValue(),'3')
 }
 const needs=page.locator('details').filter({has:page.locator('summary').getByText('必要なカード',{exact:true})})
 await needs.locator('summary').click()
 await visible(needs.locator('a[lang=en]').getByText(titles.en,{exact:true}))
 await visible(needs.locator('.card-text-credit').filter({hasText:'カード名の言語 · 英語'}))
 page.once('dialog',d=>d.accept())
 await go('/stores');await page.locator('.store-select').click();await visible(page.locator('.ol-viewport'))
 const notices=page.locator('.store-events li')
 for(const [lang,heading,tournament,restock,arrival] of [
   ['ko','향후 7일 대회·입고','대회','입고','신상품 입고'],
   ['ja','今後7日間の大会・入荷','大会','入荷','新商品の入荷'],
   ['en','Tournaments and restocks in the next 7 days','Tournament','Restock','New product arrival']
 ]){
   await select.selectOption(lang)
   await visible(page.getByRole('heading',{name:heading,exact:true}))
   await visible(notices.first().getByText(tournament,{exact:true}))
   await visible(notices.first().getByText('Store championship',{exact:true}))
   await visible(notices.last().getByText(restock,{exact:true}))
   await visible(notices.last().getByText(arrival,{exact:true}))
   assert.match(await notices.first().locator('time').innerText(),/19:00 KST/)
   assert.match(await notices.last().locator('time').innerText(),/22:30 KST/)
   assert.equal(await notices.first().locator('a').getAttribute('href'),'https://example.invalid/official-store-event')
   assert.equal(await notices.last().locator('a').getAttribute('href'),'https://example.invalid/store-restock')
   await fits()
 }
 await go('/admin')
 await select.selectOption('en')
 await btn('Catalog editor').click()
 const selectCard=()=>page.locator('.admin-catalog-list button').filter({hasText:'수집 카드 QA'}).click()
 await selectCard()
 const trans=page.locator('.card-translations')
 const expand=async()=>{await trans.locator('summary').click();await visible(trans.locator('fieldset'))}
 await expand();await trans.getByLabel('Language to edit').selectOption('ja')
 assert.equal(await trans.getByLabel('Card name',{exact:true}).inputValue(),translation.name)
 await trans.getByLabel('Card name',{exact:true}).fill('編集中')
 await trans.getByLabel('Language to edit').selectOption('ko')
 assert.equal(await trans.getByLabel('Card name',{exact:true}).inputValue(),'')
 // Drafts survive other languages and selecting a different editor tab.
 await btn('Back to list').click();await selectCard();await expand()
 await trans.getByLabel('Language to edit').selectOption('ja')
 assert.equal(await trans.getByLabel('Card name',{exact:true}).inputValue(),'編集中')
 await trans.getByRole('button',{name:'Save language entry'}).click()
 await visible(trans.locator('.translation-conflict').getByText('別の編集',{exact:true}))
 if(process.env.QA_SCREENSHOTS)await trans.screenshot({path:join(process.env.QA_SCREENSHOTS,'admin-translation-conflict-360.png')})
 assert.equal(await trans.getByLabel('Card name',{exact:true}).inputValue(),'編集中')
 await trans.getByRole('button',{name:'Save my edit over this version'}).click()
 await visible(trans.getByRole('status').getByText('Language entry saved.'))
 assert.equal(translation.name,'編集中')
 await trans.getByLabel('Card name',{exact:true}).fill('')
 await trans.getByRole('button',{name:'Remove this language entry'}).click()
 await visible(trans.getByRole('status').getByText('Language entry removed.'))
 assert.equal(translation.version,4);assert.equal(translation.name,'');await fits()
 await select.selectOption('ja');await visible(trans.getByLabel('編集する言語'))
 await select.selectOption('ko');await visible(trans.getByLabel('보완할 언어'))
 await select.selectOption('en')
 const sourcesTab=page.locator('.admin-tabs button').nth(1)
 await sourcesTab.click()
 const sourceForm=page.locator('.x-source')
 await sourceForm.locator('summary').click()
 await sourceForm.getByLabel('X username').fill('@qa_decks')
 await sourceForm.locator('#source-game').selectOption('ONEPIECE')
 await sourceForm.locator('#source-store-search').fill('not-a-store')
 await visible(sourceForm.getByRole('button',{name:'Continue without a store'}))
 assert.equal(await sourceForm.getByRole('button',{name:'Add subscription'}).isDisabled(),true)
 await sourceForm.locator('#source-store-search').fill('Fixture')
 await sourceForm.locator('#source-store-choice').selectOption('8')
 await btn('Add subscription').click()
 await visible(page.getByRole('heading',{name:'@qa_decks'}))
 assert.deepEqual(writes.filter(x=>x.api==='admin/sources/x')[0].body,{username:'qa_decks',gameCode:'ONEPIECE',storeId:8})
 await sourceForm.getByLabel('X username').fill('qa_decks');await btn('Add subscription').click()
 await visible(sourceForm.getByRole('alert').filter({hasText:'already subscribed'}))
 await sourceForm.getByLabel('X username').fill('invalid_store');await btn('Add subscription').click()
 await visible(sourceForm.getByRole('alert').filter({hasText:'Check the X username, game and store.'}))
 await sourceForm.getByLabel('X username').fill('qa_all');await btn('Add subscription').click()
 await visible(page.getByRole('heading',{name:'@qa_all'}))
 assert.deepEqual(writes.filter(x=>x.api==='admin/sources/x').pop().body,{username:'qa_all',gameCode:null,storeId:null})
 await select.selectOption('ja');await visible(sourceForm.getByLabel('Xユーザー名'))
 await select.selectOption('ko');await visible(sourceForm.getByLabel('X 사용자명'));await fits()
 await select.selectOption('en');await btn('Server controls').click();await visible(page.getByText('TEST_ACTION'));assert.equal(await btn('Shut down server').isDisabled(),true)
 await btn('Member roles').click();await visible(page.getByText('fixture@example.invalid'))
 await btn('Posts').click();await visible(page.getByText('Fixture post'))
 await btn('Stores').click();await visible(page.getByText('Fixture shop'))
 await select.selectOption('ja');await visible(btn('店舗を登録'));await fits()
 fixtureRole='ROLE_USER';await page.reload();await visible(page.getByRole('alert'))
 assert.equal(await page.locator('.x-source').count(),0)
 assert.deepEqual(errors,[])
 console.log('360px Chrome passed: Korean, English and Japanese in binder, unsaved and edited decks, search, catalog and play; per-field source links, language fallback and reference image priority; pinned variant and edited quantities survive language changes; six deck curves and hands, One Piece play, store events and administrator controls.')
}finally{await browser.close()}
