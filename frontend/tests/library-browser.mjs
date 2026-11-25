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
const card = {id:81,name:'달빛 카드',number:'QA-81',gameCode:'YUGIOH',image}
const game = {code:'YUGIOH',name:'유희왕'}
const rule = {version:2,sections:[{section:'MAIN',minCards:40,maxCards:60}]}
const deck = {id:72,name:'연습 덱',gameCode:game.code,state:'DRAFT',revision:1,cards:1,updatedAt:'2026-10-10T00:00:00Z',shareToken:null,rule,
  entries:[{cardId:card.id,name:card.name,number:card.number,section:'MAIN',quantity:1,image}]}
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
  let writes=0, rejectSave=false, quantity=2, createCount=0
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
      if(api==='me/binder')return respond({items:owned,total:24,copies:24,page:0})
      if(api==='me/binder/'+card.id){
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
  const savedDeck=()=>page.getByRole('spinbutton',{name:card.name+' 수량'})
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
  await page.goto(host+'/decks')
  await link(deck.name).click()
  await visible(savedDeck())
  await savedDeck().fill('2')
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
  await button('메뉴').click()
  await link('바인더').click()
  await menuDismissed
  assert.equal(await savedDeck().inputValue(),'2')
  const logoutDismissed=dismissNext()
  await button('로그아웃').click()
  await logoutDismissed
  assert.equal(await savedDeck().inputValue(),'2')
  await button('이 덱으로 연습').click()
  const choice=page.getByRole('dialog',{name:'어떤 구성으로 연습할까요?'})
  await visible(choice)
  await capture('deck-practice-360-light')
  await page.emulateMedia({colorScheme:'dark'})
  await capture('deck-practice-360-dark')
  await page.emulateMedia({colorScheme:'light'})
  await button('편집 계속').click()
  assert.equal(await savedDeck().inputValue(),'2')
  await button('이 덱으로 연습').click()
  rejectSave=true
  await button('변경 저장 후 연습').click()
  await visible(page.getByRole('alert').filter({hasText:'테스트 저장 오류'}))
  assert.equal(await savedDeck().inputValue(),'2')
  rejectSave=false
  await button('이 덱으로 연습').click()
  await button('변경 버리고 저장본으로 연습').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 1'))
  assert.equal(writes,0)
  await page.goBack()
  await visible(savedDeck())
  await savedDeck().fill('3')
  await button('이 덱으로 연습').click()
  await button('변경 저장 후 연습').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 3'))
  assert.equal(writes,1)

  await page.goto(host+'/decks/new')
  await page.getByRole('textbox',{name:'덱 이름'}).fill('그림 덱')
  await button(card.name+' 추가').click()
  assert.equal(await page.locator('.lib-recipe .lib-thumbnail').count(),1)
  const downloaded=page.waitForEvent('download')
  await button('PNG 저장').click()
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
  await button('임시 저장 후 연습').click()
  await onPath('/play')
  await visible(page.getByText(card.name+' × 1'))
  assert.equal(createCount,1)

  await page.goto(host+'/decks/new?game=YUGIOH&card='+card.id)
  await visible(page.locator('.lib-recipe .lib-thumbnail'))
  assert.ok(await page.locator('.lib-recipe .lib-thumbnail').evaluate(el=>el.style.backgroundImage.includes('/media/sheets/test.webp')))
  const discard=page.waitForEvent('dialog').then(d=>d.accept())
  await link('내 덱 목록').click()
  await discard
  await onPath('/decks')

  await page.goto(host+'/binder')
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
  await input.fill('5')
  await button('수량 저장').click()
  await page.getByText(card.name+' 5장을 저장했습니다.').waitFor()
  assert.equal(quantity,5)
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),360)
  assert.deepEqual(errors,[])
  console.log('360×800 Chrome passed: back/menu/logout cancel; practice cancel, failed save, saved revision and save-and-play; new-deck practice; pre-save PNG with '+redPixels+' matching art pixels; 24-row binder dialog, autofocus, cancel focus restoration and save.')
} finally {
  await browser.close()
}
