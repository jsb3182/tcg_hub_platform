import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,join} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=fileURLToPath(new URL('../dist/',import.meta.url)),actual=process.env.ART_SIZE_QA_ORIGIN,host=actual||'http://127.0.0.1:19741'
assert.equal(new URL(host).hostname,'127.0.0.1')
const source='/media/cards/'+'a'.repeat(64)+'.webp'
const card=actual?await (await fetch(host+'/api/v1/cards/'+Number(process.env.ART_SIZE_CARD_ID)+'?lang=ko')).json():
  {id:15,gameCode:'YUGIOH',name:'검증용 카드',language:'ko',imageUrl:source,imageLanguage:'ko',number:'QA-015',variants:[],specs:{type:'Normal Monster',level:7,atk:2200,def:1100}}
if(actual){assert.match(card.imageUrl,/^\/media\/cards\/[a-f0-9]{64}\.webp$/);assert.equal(card.imageLanguage,'ko')}
const mime={'.js':'text/javascript','.css':'text/css','.png':'image/png','.html':'text/html;charset=utf-8'}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH})
try{for(const width of [320,360,768,1280]){
  const ctx=await browser.newContext({viewport:{width,height:800},isMobile:width<=768,deviceScaleFactor:1,serviceWorkers:'block'})
  const page=await ctx.newPage();page.setDefaultTimeout(4500)
  const png=Buffer.from(await page.evaluate(()=>{
    const c=document.createElement('canvas');c.width=1488;c.height=2079
    const g=c.getContext('2d');g.fillStyle='#dbcda9';g.fillRect(0,0,c.width,c.height);g.fillStyle='#4e5d77';g.fillRect(80,160,1328,1120);g.fillStyle='#384551';g.fillRect(85,1410,1170,35);g.fillRect(85,1510,1060,35)
    return c.toDataURL('image/png').split(',')[1]
  }),'base64')
  await ctx.route('**/*',async route=>{
    const url=new URL(route.request().url()),p=url.pathname,json=v=>route.fulfill({json:v})
    if(url.origin!==host)return route.abort()
    if(p===source)return route.fulfill({body:png,contentType:'image/png'})
    if(p.includes('/auth/refresh'))return json({accessToken:'test',email:'sample@example.invalid',role:'ROLE_USER'})
    if(p.includes('/auth/admin-mode'))return json({mode:'DISABLED'})
    if(actual && (p.startsWith('/media/') || /^\/api\/v1\/(?:cards|games|packs)(?:\/|$)/.test(p)))return route.continue()
    if(p.endsWith('/games'))return json([{code:'YUGIOH'}])
    if(p==='/api/v1/cards/15')return json(card)
    if(p==='/api/v1/cards')return json({items:[card],total:1})
    if(p.endsWith('/binder/stats'))return json([{gameCode:'YUGIOH',copies:1,uniqueCards:1}])
    if(p==='/api/v1/me/binder')return json({items:[{...card,cardId:card.id,edition:'ko',quantity:1,condition:'NM'}],total:1,copies:1})
    if(p.startsWith('/api/'))return json([])
    const file=extname(p)?p.slice(1):'index.html'
    return route.fulfill({body:await readFile(join(dist,file)),contentType:mime[extname(file)]})
  })
  const metrics={}
  for(const [name,path,selector] of [['list','/?lang=ko&game='+card.gameCode+'&q='+encodeURIComponent(card.number),'.card-leading img'],['detail','/cards/'+card.id+'?lang=ko','.card-reader .localized-card img'],['binder','/binder?lang=ko','.binder-pockets .lib-print img']]){
    await page.goto(host+path);await page.locator(selector).first().waitFor()
    const box=await page.locator(selector).first().evaluate(async el=>{await el.decode();const r=el.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height),document.documentElement.scrollWidth]})
    metrics[name]=box
    if(process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await page.screenshot({path:join(process.env.QA_SCREENSHOTS,name+'-'+width+'.png')})}
  }
  console.log(width,metrics)
  if(!process.env.SIZES_AUDIT_ONLY){
    for(const [name,[w,h,viewport]] of Object.entries(metrics)){
      assert.equal(viewport,width,name+' viewport')
      assert.ok(w<=(name==='list'?44:width<=420?115:172),name+' '+w)
      assert.ok(h<=w*1.5,name+' '+h)
    }
  }
  await ctx.close()
}}finally{await browser.close()}
