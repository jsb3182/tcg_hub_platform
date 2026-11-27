// Long-list and deck-editor keyboard/touch navigation against the production Vue bundle.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=fileURLToPath(new URL('../dist/',import.meta.url)),origin='http://127.0.0.1:19898'
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png'}
const decks=Array.from({length:15},(_,i)=>({id:i+1,gameCode:'YUGIOH',name:'연습 덱 '+(i+1),state:'DRAFT',updatedAt:'2026-11-01T10:00:00Z',mainCount:60,extraCount:15,sideCount:15,cards:90}))
const rule={version:2,sections:['MAIN','EXTRA','SIDE'].map(section=>({section,minCards:0,maxCards:section==='MAIN'?60:15}))}
const entries=Array.from({length:30},(_,i)=>({cardId:i+1,quantity:3,section:i<20?'MAIN':i<25?'EXTRA':'SIDE',number:'QA-'+(i+1),name:'검증용 카드 '+(i+1)}))
const deck={...decks[0],rule,entries,revision:1}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
try{
 for(const width of [360,1280]){
  const context=await browser.newContext({viewport:{width,height:800},isMobile:width===360,hasTouch:width===360,serviceWorkers:'block',reducedMotion:'reduce'})
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url()),path=url.pathname
    if(url.origin!==origin)return route.abort()
    const json=value=>route.fulfill({json:value})
    if(path.startsWith('/api/v1/')){
      const api=path.slice(8)
      if(api==='auth/refresh')return json({email:'deck@example.invalid',role:'ROLE_USER',accessToken:'fixture'})
      if(api==='auth/admin-mode')return json({mode:'DISABLED'})
      if(api==='games')return json([{code:'YUGIOH',name:'유희왕'}])
      if(api==='me/decks'){const items=url.searchParams.get('q')?[]:decks;return json({items,total:items.length,totalCards:90*items.length})}
      if(api==='me/decks/1'||api==='shared/decks/qa')return json(deck)
      if(api==='me/decks/needed')return json({items:[],next:null})
      if(api==='cards')return json({items:[],total:0,page:0,size:20})
      return json([])
    }
    const file=extname(path)?path.slice(1):'index.html'
    return route.fulfill({body:await readFile(resolve(dist,file)),contentType:mime[extname(file)]})
  })
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(7000)
  const jump=page.locator('.deck-jump'),lang=page.locator('.locale-switch select')
  const top=()=>page.waitForFunction(()=>document.scrollingElement.scrollTop<=2)
  const bottom=()=>page.waitForFunction(()=>{const s=document.scrollingElement;return s.scrollHeight-s.scrollTop-s.clientHeight<=2})
  const layout=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
  await page.goto(origin+'/decks?lang=ko')
  await page.locator('.deck-banner-list li').nth(14).waitFor().catch(async e=>{throw new Error(e.message+' '+(await page.locator('body').innerText()).slice(0,380)+' '+errors.join(','))})
  await jump.waitFor().catch(async e=>{throw new Error(e.message+' '+JSON.stringify(await page.evaluate(()=>({height:document.querySelector('#content').offsetHeight,viewport:innerHeight,focus:document.activeElement.tagName})))+' '+errors.join(','))})
  for(const [l,up,down] of [['en','Top','Bottom'],['ja','先頭','末尾'],['ko','맨 위','맨 아래']]){
    await lang.selectOption(l)
    const upward=jump.getByRole('button',{name:up}),downward=jump.getByRole('button',{name:down})
    await downward.focus();await page.keyboard.press('Enter');await bottom()
    assert.ok(await downward.evaluate(e=>e===document.activeElement))
    await page.keyboard.press('Shift+Tab');assert.ok(await upward.evaluate(e=>e===document.activeElement))
    await page.keyboard.press('Space');await top();await layout()
  }
  const search=page.getByRole('searchbox').first()
  await search.fill('empty');await jump.waitFor({state:'hidden'})
  await page.getByText('조건에 맞는 덱이 없습니다.').waitFor();await search.blur()
  assert.equal(await jump.count(),0)
  await page.goto(origin+'/decks/1?lang=ko');await jump.waitFor()
  const qty=page.locator('.lib-controls input').first();await qty.fill('2');await jump.waitFor({state:'hidden'})
  await qty.blur();await jump.waitFor()
  await page.getByRole('button',{name:'이 덱으로 연습'}).click();await page.locator('dialog[open]').waitFor()
  await jump.waitFor({state:'hidden'});await page.getByRole('button',{name:'편집 계속'}).click()
  await jump.waitFor();assert.equal(await qty.inputValue(),'2')
  await page.emulateMedia({reducedMotion:'no-preference'})
  await jump.getByRole('button',{name:'맨 아래'}).click();await bottom();await layout()
  await jump.getByRole('button',{name:'맨 위'}).click();await top()
  if(process.env.QA_SCREENSHOTS){
    await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
    await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,'deck-jump-'+width+'.png')})
  }
  page.once('dialog',d=>d.accept())
  await page.goto(origin+'/shared/decks/qa?lang=ja');await jump.getByRole('button',{name:'末尾'}).click();await bottom()
  await page.goto(origin+'/news');assert.equal(await jump.count(),0)
  assert.deepEqual(errors,[]);console.log(width+'px: 15 decks; 60/15/15 editor and shared recipe; three languages; keyboard, reduced motion, edits, dialogs and short pages passed.')
  await context.close()
 }
}finally{await browser.close()}
