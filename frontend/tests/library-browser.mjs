// Run after npm run build with Playwright and Chromium installed.
// PLAYWRIGHT_MODULE, CHROME_PATH and QA_SCREENSHOTS can point to existing local test tools.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, readFile } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const dist = fileURLToPath(new URL('../dist/', import.meta.url))
const host = 'http://127.0.0.1:19713'
const mime = {'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.webmanifest':'application/manifest+json'}
const csp = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'"
const image = {url:'/media/sheets/test.webp',sheetId:1,col:1,row:1,cellWidth:30,cellHeight:44}
const card = {id:81,name:'달빛 카드',number:'QA-81',gameCode:'YUGIOH',curveValue:5,image}
const game = {code:'YUGIOH',name:'유희왕'}
const rule = {version:2,sections:[{section:'MAIN',minCards:40,maxCards:60}]}
const deck = {id:72,name:'연습 덱',gameCode:game.code,state:'DRAFT',revision:1,cards:1,updatedAt:'2026-10-10T00:00:00Z',shareToken:null,rule,
  entries:[{cardId:card.id,name:card.name,number:card.number,section:'MAIN',quantity:1,curveValue:5,image}]}
const owned = Array.from({length:24},(_,i)=>({cardId:i+1,name:'소장 카드 '+(i+1),quantity:1}))
const expectedToken = 'Bearer fixture-library'
const browser = await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || undefined})
try {
  const context = await browser.newContext({viewport:{width:360,height:800},deviceScaleFactor:1,isMobile:true,
    hasTouch:true,locale:'ko-KR',serviceWorkers:'block',acceptDownloads:true})
  const page = await context.newPage()
  page.setDefaultTimeout(9000)
  const errors = []
  page.on('pageerror',error=>errors.push(error.message))
  const atlas = await page.evaluate(()=>{
    const sheet=document.createElement('canvas')
    sheet.width=120; sheet.height=132
    const g=sheet.getContext('2d')
    g.fillStyle='#181818';g.fillRect(0,0,120,132)
    g.fillStyle='#dc244d';g.fillRect(30,44,30,44)
    return sheet.toDataURL('image/webp',1).split(',')[1]
  })
  let writes=0, rejectSave=false, quantity=2, createCount=0, pendingLotEdit
  await context.route('**/*',async route=>{
    const req=route.request(), url=new URL(req.url())
    if(url.origin!==host)return route.abort()
    const path=url.pathname
    const respond=(obj,status=200)=>route.fulfill({json:obj,status})
    if(path.startsWith('/api/v1/')){
      const api=path.slice(8), method=req.method()
      if(api==='auth/refresh')return respond({role:'ROLE_USER',email:'deck@example.invalid',accessToken:'fixture-library'})
      if(api==='auth/admin-mode')return respond({mode:'DISABLED'})
      if(api==='games')return respond([game])
      if(api==='cards')return respond({items:[card],total:1,size:8,page:0})
      if(api==='cards/'+card.id)return respond({...card,image:undefined,variants:[{image:null},{image}]})
      if(api==='play/cards')return respond([{...card,language:'ko'}])
      assert.equal(req.headers().authorization,expectedToken)
      if(api==='me/decks/rules/YUGIOH')return respond(rule)
      if(api==='me/decks' && method==='GET')return respond({items:[deck],total:1})
      if(api==='me/decks' || api==='me/decks/'+deck.id){
        if(method==='GET')return respond(deck)
        if(rejectSave)return respond({detail:'테스트 저장 오류'},422)
        const data=req.postDataJSON()
        if(method==='POST')createCount++
        writes++
        Object.assign(deck,{name:data.name,state:data.state,revision:deck.revision+1,
          entries:data.entries.map(e=>({...e,name:card.name,number:card.number,image}))})
        return respond(deck)
      }
      if(api==='me/binder/stats')return respond([{gameCode:'YUGIOH',uniqueCards:24,copies:24}])
      if(api==='me/binder')return respond({items:owned,total:24,copies:24,page:0})
      if(api==='me/binder/'+card.id){
        if(method==='GET' && url.searchParams.get('edition')==='ko')await pendingLotEdit
        if(method==='PUT'){assert.equal(req.postDataJSON().expectedQuantity,quantity);quantity=req.postDataJSON().quantity}
        return respond({quantity})
      }
      errors.push('Unknown API '+api)
      return respond({},404)
    }
    if(path===image.url)return route.fulfill({contentType:'image/webp',body:Buffer.from(atlas,'base64')})
    const file=path.startsWith('/assets/') || extname(path) ? path.slice(1) : 'index.html'
    try{return await route.fulfill({body:await readFile(join(dist,file)),contentType:mime[extname(file)],headers:{'Content-Security-Policy':csp}})}
    catch{return route.fulfill({status:404,body:''})}
  })
  const button=name=>page.getByRole('button',{name,exact:true})
  const link=name=>page.getByRole('link',{name,exact:true})
  const visible=el=>el.waitFor({state:'visible'})
  const savedDeck=()=>page.getByRole('spinbutton',{name:card.name+' quantity'})
  const onPath=p=>page.waitForURL(url=>url.pathname===p)
  async function capture(name){
    if(!process.env.QA_SCREENSHOTS)return
    await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
    await page.screenshot({path:join(process.env.QA_SCREENSHOTS,name+'.png')})
  }
  function dismissNext(){
    const handled=page.waitForEvent('dialog').then(async d=>{assert.equal(d.type(),'confirm');await d.dismiss()})
    return handled
  }
  const opening=page.locator('.practice-setup input[type=number]')
  const language=page.getByRole('combobox',{name:'한국어 · English · 日本語'})
  await page.goto(host+'/play?lang=unavailable')
  assert.equal(await language.inputValue(),'ko')
  assert.equal(await opening.inputValue(),'5')
  await page.goto(host+'/play?game=POKEMON&lang=ja')
  assert.equal(await opening.inputValue(),'7')
  await opening.fill('6')
  await language.selectOption('en')
  await visible(link('Choose a saved deck'))
  assert.equal(await opening.inputValue(),'6')
  await button('Yu-Gi-Oh!').click()
  await page.waitForURL(url=>url.searchParams.get('game')==='YUGIOH')
  assert.equal(await opening.inputValue(),'5')
  await button('Pokémon').click()
  await page.waitForURL(url=>url.searchParams.get('game')==='POKEMON')
  assert.equal(await opening.inputValue(),'6')
  await link('Choose a saved deck').click()
  await onPath('/decks')
  const selectedLanguage=()=>new URL(page.url()).searchParams.get('lang')
  assert.equal(selectedLanguage(),'en')
  await link(deck.name).click()
  await visible(savedDeck())
  assert.equal(selectedLanguage(),'en')
  const localDraw=page.locator('.opening-panel')
  await localDraw.getByRole('button').click()
  assert.equal(await localDraw.locator('.sample-hand li').count(),1)
  await savedDeck().fill('2')
  await localDraw.locator('.sample-hand').waitFor({state:'hidden'})
  assert.match(await page.locator('.curve-list').innerText(),/5\s+2/)
  await localDraw.getByRole('button').click()
  assert.equal(await localDraw.locator('.sample-hand li').count(),2)
  const reloadDismissed=page.waitForEvent('dialog').then(async d=>{assert.equal(d.type(),'beforeunload');await d.dismiss()})
  await page.evaluate(()=>location.reload())
  await reloadDismissed
  assert.equal(await savedDeck().inputValue(),'2')
  const backDismissed=dismissNext()
  await page.evaluate(()=>history.back())
  await backDismissed
  await onPath('/decks/72')
  assert.equal(await savedDeck().inputValue(),'2')
  const menuDismissed=dismissNext()
  await button('Menu').click()
  await link('Binder').click()
  await menuDismissed
  assert.equal(await savedDeck().inputValue(),'2')
  const logoutDismissed=dismissNext()
  await button('Sign out').click()
  await logoutDismissed
  assert.equal(await savedDeck().inputValue(),'2')
  await button('Practice with this deck').click()
  const choice=page.getByRole('dialog',{name:'Which deck do you want to practice with?'})
  await visible(choice)
  await capture('deck-practice-360-light')
  await page.emulateMedia({colorScheme:'dark'})
  await capture('deck-practice-360-dark')
  await page.emulateMedia({colorScheme:'light'})
  await button('Keep editing').click()
  assert.equal(await savedDeck().inputValue(),'2')
  await button('Practice with this deck').click()
  rejectSave=true
  await button('Save changes and practice').click()
  await visible(page.getByRole('alert').filter({hasText:'테스트 저장 오류'}))
  assert.equal(await savedDeck().inputValue(),'2')
  rejectSave=false
  await button('Practice with this deck').click()
  await button('Discard changes and practice saved deck').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 1'))
  assert.equal(selectedLanguage(),'en')
  assert.equal(await opening.inputValue(),'5')
  assert.equal(writes,0)
  await page.goBack()
  await visible(savedDeck())
  await savedDeck().fill('3')
  await button('Practice with this deck').click()
  await button('Save changes and practice').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 3'))
  assert.equal(selectedLanguage(),'en')
  assert.equal(writes,1)

  await page.goto(host+'/decks/new?lang=ja')
  await page.getByRole('textbox',{name:'デッキ名'}).fill('그림 덱')
  await button(card.name+' を追加').click()
  assert.equal(await page.locator('.lib-recipe .lib-thumbnail').count(),1)
  const downloaded=page.waitForEvent('download')
  await button('PNGで保存').click()
  const stream=await (await downloaded).createReadStream()
  const chunks=[]
  for await(const chunk of stream)chunks.push(chunk)
  const png=Buffer.concat(chunks)
  assert.equal(png.subarray(1,4).toString(),'PNG')
  const redPixels=await page.evaluate(async b64=>{
    const img=new Image()
    img.src='data:image/png;base64,'+b64
    await img.decode()
    const c=document.createElement('canvas')
    c.width=img.width;c.height=img.height
    const g=c.getContext('2d')
    g.drawImage(img,0,0)
    const pixels=g.getImageData(0,0,c.width,c.height).data
    let count=0
    for(let i=0;i<pixels.length;i+=4)if(pixels[i]>170&&pixels[i+1]<80&&pixels[i+2]>40&&pixels[i+2]<120)count++
    return count
  },png.toString('base64'))
  assert.ok(redPixels>100,'exported PNG contains the selected atlas cell')
  assert.equal(writes,1)
  await button('下書きを保存して練習').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 1'))
  assert.equal(createCount,1)
  assert.equal(selectedLanguage(),'ja')
  assert.equal(await language.inputValue(),'ja')

  await page.goto(host+'/decks/new?game=YUGIOH&card='+card.id)
  await visible(page.locator('.lib-recipe .lib-thumbnail'))
  assert.ok(await page.locator('.lib-recipe .lib-thumbnail').evaluate(el=>el.style.backgroundImage.includes('/media/sheets/test.webp')))
  const discard=page.waitForEvent('dialog').then(d=>d.accept())
  await link('デッキ一覧').click()
  await discard
  await onPath('/decks')

  await page.goto(host+'/binder')
  await language.selectOption('ko')
  const pick=button(card.name+' 추가')
  await pick.click()
  const dialog=page.getByRole('dialog',{name:card.name})
  const input=dialog.getByRole('spinbutton',{name:'보유 수량'})
  await visible(input)
  assert.ok(await input.evaluate(el=>el===document.activeElement))
  assert.equal(await input.inputValue(),'3')
  await capture('binder-quantity-360')
  assert.ok(await dialog.evaluate(el=>el.getBoundingClientRect().top>=0 && el.getBoundingClientRect().bottom<=innerHeight))
  await page.keyboard.press('Escape')
  assert.ok(await pick.evaluate(el=>el===document.activeElement))
  await pick.click()
  let releaseLotLookup
  pendingLotEdit=new Promise(resolve=>{releaseLotLookup=resolve})
  await dialog.getByRole('combobox',{name:/언어판/}).selectOption('ko')
  await input.fill('5')
  assert.ok(await button('수량 저장').isDisabled())
  releaseLotLookup()
  await button('수량 저장').click()
  await page.getByText(card.name+' 5장을 저장했습니다.').waitFor()
  assert.equal(quantity,5)
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),360)
  await page.goto(host+'/play?game=POKEMON&lang=en&lang=ko')
  assert.equal(await language.inputValue(),'ko')
  assert.equal(await opening.inputValue(),'6')
  assert.deepEqual(errors,[])
  console.log('360×800 Chrome passed: 5/7 opening defaults and per-game custom size; language through deck selection, discard, save-and-play and new decks; back/menu/logout cancel, failed save; pre-save PNG with '+redPixels+' matching art pixels; binder quantity and focus.')
} finally {
  await browser.close()
}
