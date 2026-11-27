import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {join,extname} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=fileURLToPath(new URL('../dist/',import.meta.url)),origin='http://127.0.0.1:19714'
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH})
const games=['YUGIOH','POKEMON','ONEPIECE','WEISS','NIVEL','RIFTBOUND'],rules={version:1,sections:[{section:'MAIN',minCards:1,maxCards:60},{section:'LEADER',minCards:1,maxCards:1}]}
const p={id:78,cardId:78,number:'OP15-001',name:'후보 카드',gameCode:'ONEPIECE',language:'ko'}
try{for(const width of [360,1280]){
 const context=await browser.newContext({viewport:{width,height:800},isMobile:width===360,serviceWorkers:'block'})
 const page=await context.newPage();page.setDefaultTimeout(6000)
 const errors=[],requests=[],png=Buffer.from(await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=240;canvas.height=320
   const g=canvas.getContext('2d');g.fillStyle='#7b5862';g.fillRect(0,0,240,320);return canvas.toDataURL().split(',')[1]}),'base64')
 let created
 page.on('pageerror',e=>errors.push(e.message))
 await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),path=url.pathname,body=req.method()==='POST' && req.headers()['content-type']?.startsWith('application/json')?req.postDataJSON():null
   if(url.origin!==origin)return route.abort()
   if(path.startsWith('/api/')){
     requests.push({path,method:req.method(),body});const json=data=>route.fulfill({json:data})
     if(path.endsWith('/auth/refresh'))return json({accessToken:'fixture',role:'ROLE_USER',email:'deck@example.invalid'})
     if(path.endsWith('/auth/admin-mode'))return json({mode:'DISABLED'})
     if(path.endsWith('/games'))return json(games.map(code=>({code})))
     if(path==='/api/v1/me/decks'&&req.method()==='GET')return json({items:[],total:0,totalCards:0,allTotal:4})
     if(path==='/api/v1/me/decks'){created={...body,id:9,revision:1,rule:rules,updatedAt:'2026-01-01T00:00:00Z',entries:body.entries.map(e=>({...p,...e}))};return json(created)}
     if(path==='/api/v1/me/decks/9')return json(created)
     if(path.startsWith('/api/v1/me/decks/rules/'))return json(rules)
     if(path==='/api/decks/import-capture'){
       assert.equal(req.headers().authorization,'Bearer fixture');assert.equal(req.headers()['x-tcg-request'],'1')
       assert.match(req.headers()['content-type'],/^multipart\/form-data;/)
       const bytes=req.postDataBuffer().toString('latin1');assert.match(bytes,/name="game"\r\n\r\nONEPIECE/)
       return json({width:240,height:320,slots:[{index:0,left:0,top:0,width:240,height:320,needsReview:true,candidates:[p]}]})
     }
     if(path==='/api/v1/cards')return json({items:[p],total:1})
     if(path.endsWith('/needed'))return json({items:[],next:null})
     return json([])
   }
   const f=extname(path)?path.slice(1):'index.html'
   return route.fulfill({body:await readFile(join(dist,f)),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html;charset=utf-8','.png':'image/png'})[extname(f)]})
 })
 await page.goto(origin+'/decks?lang=ko')
 await page.locator('.deck-add').click()
 const sheet=page.locator('.create-sheet[open]')
 await sheet.getByLabel('한국어 이름 (필수)').fill('검수한 덱')
 await sheet.getByLabel('일본어 이름').fill('自作デッキ')
 await sheet.getByLabel('영어 이름').fill('Reviewed deck')
 for(const g of games){
   await sheet.locator('.sheet-fields>label select').selectOption(g)
   const captureToggle=sheet.locator('.sheet-fields>details')
   if(!await captureToggle.evaluate(el=>el.open))await captureToggle.locator('summary').click()
   await sheet.locator('.capture-panel input[type=file]').waitFor()
 }
 await sheet.locator('.sheet-fields>label select').selectOption('ONEPIECE')
 if(!await sheet.locator('.sheet-fields>details').evaluate(el=>el.open))await sheet.locator('.sheet-fields>details>summary').click()
 await sheet.locator('.capture-panel input[type=file]').waitFor()
 await sheet.locator('.capture-panel input[type=file]').setInputFiles({name:'sample.png',mimeType:'image/png',buffer:png})
 const grid=sheet.locator('.grid-import');await grid.getByLabel('가로 칸').fill('1');await grid.getByLabel('세로 칸').fill('1')
 await grid.getByRole('button',{name:'서버의 카드와 대조'}).click()
 await sheet.locator('.capture-match').click()
 await sheet.locator('.capture-candidates button').click()
 await sheet.locator('.capture-panel').getByRole('button',{name:'확인한 카드를 덱에 추가'}).click()
 await sheet.locator('.staged-cards').getByLabel('구역').selectOption('LEADER')
 await sheet.getByLabel('대표 이미지').setInputFiles({name:'cover.png',mimeType:'image/png',buffer:png})
 await sheet.locator('.banner-art').waitFor()
 assert.equal(await sheet.locator('.banner-names strong').textContent(),'검수한 덱')
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
 if(process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await sheet.screenshot({path:join(process.env.QA_SCREENSHOTS,'new-deck-'+width+'.png')})}
 await sheet.getByRole('button',{name:'만들기',exact:true}).click()
 await page.waitForURL(u=>u.pathname==='/decks/9')
 assert.equal(created.entries[0].cardId,78);assert.equal(created.entries[0].section,'LEADER');assert.equal(created.nameEn,'Reviewed deck')
 assert.ok(requests.some(r=>r.path.endsWith('/decoration/cover') && r.method==='POST'))
 assert.deepEqual(errors,[]);console.log(width+'px: six game capture entry points, grid upload, manual candidate, multilingual banner preview, cover and draft saved.');await context.close()
}}finally{await browser.close()}
