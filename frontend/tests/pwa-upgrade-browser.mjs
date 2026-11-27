// Pass the previous release JAR (or its extracted static directory). An optional second, eager
// release reproduces the original bug. PWA_CANDIDATE_DIST can also point to the final JAR.
import assert from 'node:assert/strict'
import {createServer} from 'node:http'
import {createRequire} from 'node:module'
import {readFile,readdir,stat} from 'node:fs/promises'
import {extname,join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {unzipSync} from 'fflate'
const previous=process.argv[2], eager=process.argv[3], candidate=process.env.PWA_CANDIDATE_DIST||fileURLToPath(new URL('../dist/',import.meta.url))
assert.ok(previous,'Usage: node tests/pwa-upgrade-browser.mjs PREVIOUS_RELEASE [EAGER_RELEASE]')
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
const mime={'.js':'application/javascript','.css':'text/css','.html':'text/html;charset=utf-8','.webmanifest':'application/manifest+json','.png':'image/png'}
async function bundle(input){
  const files=new Map()
  if((await stat(input)).isFile()){
    const prefix='BOOT-INF/classes/static/'
    const extracted=unzipSync(await readFile(input),{filter:e=>e.name.startsWith(prefix)&&!e.name.endsWith('/')})
    for(const [name,bytes] of Object.entries(extracted))files.set(name.slice(prefix.length),Buffer.from(bytes))
  }else{
    async function walk(dir,relative=''){
      await Promise.all((await readdir(dir,{withFileTypes:true})).map(async e=>{
        const name=relative+e.name,path=join(dir,e.name)
        if(e.isDirectory())await walk(path,name+'/')
        else files.set(name,await readFile(path))
      }))
    }
    await walk(input)
  }
  const asset=pattern=>[...files.keys()].find(n=>pattern.test(n))?.slice('assets/'.length)
  const chunk=asset(/^assets\/ReleasesView-.*\.js$/), index=asset(/^assets\/index-.*\.js$/)
  assert.ok(chunk&&index&&files.get('sw.js')?.toString().includes('assets/'+index),'Incomplete release bundle: '+input)
  return {files,chunk,index}
}
async function scenario(first,next,{reproduce=false,cold=false}={}){
 const releases=[first,next]
 const missing=[], serverErrors=[]
 let version=0
 let disconnected=false
 let resumeUpdate,noticeUpdate
 const holdUpdate=new Promise(resolve=>{resumeUpdate=resolve})
 const updateStarted=new Promise(resolve=>{noticeUpdate=resolve})
 const game={code:'YUGIOH',name:'유희왕'}
 const pack={id:1,name:'업데이트 검증 팩',code:'PWA-01',gameCode:'YUGIOH',group:'SCHEDULE',total:1}
 const server=createServer(async(req,res)=>{
   if(disconnected){res.destroy();return}
   const path=new URL(req.url,'http://localhost').pathname
   const send=(status,type,body)=>{res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store'});res.end(body)}
   const json=(v,status=200)=>send(status,'application/json',JSON.stringify(v))
   try{
     if(path.startsWith('/api/')){
       const api=path.slice('/api/v1/'.length)
       if(api==='auth/refresh')return json({email:'update@example.invalid',role:'ROLE_USER',accessToken:'fixture'})
       if(api==='auth/admin-mode')return json({mode:'DISABLED'})
       if(api==='games')return json([game])
       if(api==='releases')return json([pack])
       if(api==='packs')return json([])
       if(api==='cards')return json({items:[],total:0,page:0,size:20})
       if(api==='me/decks/rules/YUGIOH')return json({version:1,sections:[{section:'MAIN',minCards:40,maxCards:60}]})
       return json({},404)
     }
     const release=releases[version], file=extname(path)?path.slice(1):'index.html'
     if(cold&&version===1&&path==='/sw.js'){noticeUpdate();await holdUpdate}
     const data=release.files.get(file)
     if(!data){missing.push(path);return send(404,'text/plain','missing')}
     send(200,mime[extname(file)]||'application/octet-stream',data)
   }catch(e){serverErrors.push(e.message);send(500,'text/plain','test origin error')}
 })
 await new Promise((ok,no)=>server.once('error',no).listen(0,'127.0.0.1',ok))
 const origin='http://127.0.0.1:'+server.address().port
 const ctx=await browser.newContext({viewport:{width:360,height:800},isMobile:true,hasTouch:true,serviceWorkers:'allow'})
 try{
   let home=await ctx.newPage()
   const errors=[];home.on('pageerror',e=>errors.push(e.message))
   // Observe activation without keeping an app document open under the worker's scope.
   const observer=await ctx.newPage(), protocol=await ctx.newCDPSession(observer)
   const versions=new Map(),changes=[]
   protocol.on('ServiceWorker.workerVersionUpdated',({versions:items})=>{
     for(const item of items)if(item.scriptURL===origin+'/sw.js'){
       if(versions.get(item.versionId)!==item.status)changes.push([item.versionId,item.status])
       versions.set(item.versionId,item.status)
     }
   })
   await protocol.send('ServiceWorker.enable')
   const docUrl=page=>page.evaluate(()=>document.querySelector('script[type=module]').src.split('/').pop())
   const navigate=async(page,path)=>{
     await page.locator('.menu-switch').click()
     await page.locator('#site-navigation a[href="'+path+'"]').click()
   }
   const controller=page=>page.waitForFunction(()=>!!navigator.serviceWorker.controller)
   await home.goto(origin+'/')
   await home.getByRole('heading',{name:'카드 도감',exact:true}).waitFor()
   await controller(home)
   assert.equal(await docUrl(home),releases[0].index)
   const oldPath='/assets/'+releases[0].chunk
   assert.ok(await home.evaluate(async p=>!!await caches.match(p),oldPath))
   const editor=await ctx.newPage()
   if(cold){
     // The old window is gone before the origin changes, as with an icon launch after installing an APK.
     await home.close()
     version=1;home=await ctx.newPage()
     home.on('pageerror',e=>errors.push(e.message))
     await home.goto(origin+'/');await home.getByRole('heading',{name:'카드 도감',exact:true}).waitFor()
     assert.equal(await docUrl(home),releases[0].index)
   }
   const initialWorker=ctx.serviceWorkers().find(w=>w.url()===origin+'/sw.js')
   assert.ok(initialWorker)
   const oldController=await home.evaluateHandle(()=>navigator.serviceWorker.controller)
   const homeStarted=await home.evaluate(()=>performance.timeOrigin)
   const firstChunk=()=>home.waitForResponse(r=>new URL(r.url()).pathname===oldPath)
   await editor.goto(origin+'/decks/new')
   const name=editor.getByPlaceholder('덱 이름',{exact:true})
   await name.fill('작성 중인 덱')
   const oldEditorController=await editor.evaluateHandle(()=>navigator.serviceWorker.controller)
   const timeOrigin=await editor.evaluate(()=>performance.timeOrigin)
   version=1
   const updating=home.evaluate(async()=>{const registration=await navigator.serviceWorker.ready;await registration.update()})
   if(cold){
     await updateStarted
     const resource=firstChunk()
     await navigate(home,'/releases');await home.getByRole('link',{name:/업데이트 검증 팩/}).waitFor()
     assert.equal((await resource).fromServiceWorker(),true)
     resumeUpdate()
   }
   await updating
   if(reproduce){
     await home.waitForFunction(old=>navigator.serviceWorker.controller!==old,oldController)
     await waitUntil(async()=>!await home.evaluate(p=>caches.match(p).then(Boolean),oldPath),'Replaced chunk still cached')
     await navigate(home,'/releases')
     await home.waitForFunction(()=>document.querySelector('.menu-switch')?.getAttribute('aria-expanded')==='false')
     await waitUntil(()=>missing.includes(oldPath),'Old lazy chunk was not requested at the replacement origin')
     assert.equal(new URL(home.url()).pathname,'/')
     assert.equal(await home.locator('h1').innerText(),'카드 도감')
     console.log('Reproduced',releases[0].index,'→',releases[1].index,': worker switched, cache evicted,',oldPath,'404; first release-menu tap left the catalog open.')
   }else{
     const waiting=()=>[...versions].find(([,state])=>state==='installed')?.[0]
     await waitUntil(()=>!!waiting(),'Expected the updated worker to finish precaching')
     const pending=waiting()
     assert.equal(await home.evaluate(old=>navigator.serviceWorker.controller===old,oldController),true)
     assert.ok(await home.evaluate(async p=>!!await caches.match(p),oldPath))
     if(!cold){
       const resource=firstChunk()
       await navigate(home,'/releases')
       assert.equal((await resource).fromServiceWorker(),true)
     }
     await home.getByRole('link',{name:/업데이트 검증 팩/}).waitFor()
     assert.equal(await docUrl(home),releases[0].index)
     assert.equal(await name.inputValue(),'작성 중인 덱');assert.equal(await editor.evaluate(()=>performance.timeOrigin),timeOrigin)
     disconnected=true;await ctx.setOffline(true)
     await navigate(home,'/')
     await home.getByRole('heading',{name:'카드 도감'}).waitFor()
     await navigate(home,'/releases')
     await home.getByRole('link',{name:/업데이트 검증 팩/}).waitFor()
     assert.equal(await home.evaluate(()=>performance.timeOrigin),homeStarted)
     const offline=await ctx.newPage()
     const offlineShell=await offline.goto(origin+'/releases')
     assert.equal(offlineShell.fromServiceWorker(),true)
     await offline.getByRole('link',{name:/업데이트 검증 팩/}).waitFor()
     assert.equal(await offline.evaluate(async()=>!!await caches.match('/api/v1/auth/refresh')),false)
     await offline.close()
     assert.equal(await name.inputValue(),'작성 중인 덱');disconnected=false;await ctx.setOffline(false)
     assert.equal(versions.get(pending),'installed',JSON.stringify({changes,missing}))
     await home.close()
     assert.ok(await editor.evaluate(old=>!!old && old===navigator.serviceWorker.controller,oldEditorController))
     assert.ok(await editor.evaluate(async p=>!!await caches.match(p),oldPath))
     assert.equal(await name.inputValue(),'작성 중인 덱')
     await editor.close()
     await waitUntil(()=>versions.get(pending)==='activated','waiting worker did not activate')
     const reopened=await ctx.newPage()
     await reopened.goto(origin+'/');await controller(reopened)
     await reopened.getByRole('heading',{name:'카드 도감',exact:true}).waitFor()
     assert.equal(await docUrl(reopened),releases[1].index)
     if(releases[0].chunk!==releases[1].chunk)assert.equal(await reopened.evaluate(async p=>!!await caches.match(p),oldPath),false)
     const entered=await reopened.evaluate(()=>performance.timeOrigin)
     await navigate(reopened,'/releases');await reopened.getByRole('link',{name:/업데이트 검증 팩/}).waitFor()
     assert.equal(await reopened.evaluate(()=>performance.timeOrigin),entered)
     assert.ok(!missing.includes(oldPath))
     assert.deepEqual(errors,[])
     console.log('Passed',cold?'cold first open':'open windows',releases[0].index,'→',releases[1].index,': one menu tap, preserved form input, offline navigation, latest shell on reopening.')
   }
   assert.deepEqual(serverErrors,[])
 }finally{resumeUpdate();await ctx.close();server.closeAllConnections();await new Promise(ok=>server.close(ok))}
}
async function waitUntil(check,message){
 const deadline=Date.now()+6500
 while(!await check() && Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,25))
 assert.ok(await check(),message)
}
try{
 const [old,broken,fixed]=await Promise.all([bundle(previous),eager?bundle(eager):null,bundle(candidate)])
 if(broken)await scenario(old,broken,{reproduce:true})
 if(!process.env.PWA_REPRO_ONLY){
   await scenario(old,fixed)
   await scenario(broken||old,fixed,{cold:true})
 }
}finally{await browser.close()}
