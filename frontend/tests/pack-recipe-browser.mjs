// Build frontend first. PACK_QA_ORIGIN optionally points to a loopback QA server with the imported DBGV pack.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const dist=process.env.QA_DIST||fileURLToPath(new URL('../dist/',import.meta.url))
const actual=process.env.PACK_QA_ORIGIN
const origin=actual||'http://127.0.0.1:19892'
assert.equal(new URL(origin).hostname,'127.0.0.1')
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'}
const tile=(i)=>({url:'/media/sheets/pack-qa.png',sheetId:9,col:i%4,row:0,cellWidth:40,cellHeight:58,language:'ja'})
const fakeCards=Array.from({length:45},(_,i)=>({id:i+1,number:'QA-'+String(i+1).padStart(3,'0'),name:'합성 카드 '+(i+1),gameCode:'YUGIOH',language:'ko',
  inclusion:i<33?'NEW':'REPRINT',type:i%2?'마법':'몬스터',rarity:i%2?'R':'UR',rarities:[i%2?'R':'UR'],image:tile(i),effect:'검증용 카드 효과',effectLanguage:'ko'}))
const pack={id:7,code:'DBGV',name:'테스트 팩',gameCode:'YUGIOH',metadata:{jp:'2026-09-05',kr:'2026-12'},total:45,newCount:33,reprintCount:12,newArtCount:0,group:'SCHEDULE',page:0,size:200,hasMore:false,cards:fakeCards}
const entries=[['MAIN',3,'Effect Monster'],['MAIN',2,'Spell Card'],['EXTRA',1,'Fusion Effect Monster'],['SIDE',1,'Trap Card']].map(([section,quantity,type],i)=>({
  section,quantity,type,name:'Recipe '+(i+1),number:'DECK-0'+i,cardId:40+i,image:tile(i),
}))
const deck={id:18,gameCode:'YUGIOH',name:'테스트 덱',nameEn:'Fixture deck',nameJa:'テストデッキ',state:'DRAFT',
  entries,rule:{sections:['MAIN','EXTRA','SIDE'].map(section=>({section}))}}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
try{
  for(const width of [360,1280]){
    const ctx=await browser.newContext({viewport:{width,height:width===360?800:900},hasTouch:width===360,isMobile:width===360,serviceWorkers:'block'})
    const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message))
    const sheet=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=160;c.height=174
      const p=c.getContext('2d');['#f12d52','#226abc','#188347','#740fc0'].forEach((color,i)=>{p.fillStyle=color;p.fillRect(i*40,0,40,58)});return c.toDataURL().split(',')[1]})
    let header=pack
    if(actual){
      const res=await ctx.request.get(origin+'/api/v1/releases');assert.equal(res.status(),200)
      const h=(await res.json()).find(x=>x.code==='DBGV')
      assert.ok(h)
      header=await (await ctx.request.get(origin+'/api/v1/packs/'+h.id+'?lang=ko&page=0&size=200')).json()
      assert.deepEqual([header.total,header.newCount,header.reprintCount,header.newArtCount],[45,33,12,0])
    }
    await ctx.route('**/*',async route=>{
      const url=new URL(route.request().url())
      if(url.origin!==origin)return route.abort()
      const path=url.pathname
      const json=(obj,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(obj)})
      if(path==='/media/sheets/pack-qa.png')return route.fulfill({contentType:'image/png',body:Buffer.from(sheet,'base64')})
      if(path.startsWith('/api/v1/shared/decks/'))return json(path.endsWith('/large')?{...deck,entries:[{...entries[0],quantity:999}]}:deck)
      if(actual && (path.startsWith('/media/')||path.startsWith('/api/')))return route.continue()
      if(path==='/api/v1/auth/admin-mode')return json({mode:'DISABLED'})
      if(path==='/api/v1/auth/refresh')return json({},401)
      if(path==='/api/v1/packs/7')return json(pack)
      if(path==='/api/v1/releases')return json([pack])
      if(path.match(/^\/api\/v1\/cards\/\d+$/)){const c=fakeCards.find(x=>x.id===Number(path.split('/').pop()));return json({...c,
        nameBasis:'RELATED_PRINTING',nameReferenceUrl:'https://example.invalid/references/name',
        specs:{k:c.type,atk:1000},variants:[{id:c.id,rarity:c.rarity,image:c.image}]})}
      if(path.startsWith('/api/'))return json([])
      const f=extname(path)?path.slice(1):'index.html'
      return route.fulfill({contentType:mime[extname(f)],body:await readFile(resolve(dist,f))})
    })
    page.setDefaultTimeout(8000)
    const visible=l=>l.first().waitFor({state:'visible'})
    const noOverflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
    const save=async button=>{
      const event=page.waitForEvent('download');await button.click();const chunks=[]
      for await(const chunk of await (await event).createReadStream())chunks.push(chunk)
      const data=Buffer.concat(chunks);assert.equal(data.subarray(1,4).toString(),'PNG');return data
    }
    const colorPixels=async png=>page.evaluate(async data=>{
      const im=new Image();im.src='data:image/png;base64,'+data;await im.decode()
      const c=document.createElement('canvas');c.width=im.width;c.height=im.height
      const g=c.getContext('2d');g.drawImage(im,0,0);const px=g.getImageData(0,0,c.width,c.height).data
      let colored=0;for(let i=0;i<px.length;i+=4){if(Math.max(px[i],px[i+1],px[i+2])-Math.min(px[i],px[i+1],px[i+2])>55)colored++}
      return colored
    },png.toString('base64'))
    const shot=async name=>{if(process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,name+'-'+width+'.png')})}}
    await page.goto(origin+'/releases/'+header.id+'?lang=ko')
    const row=page.locator('.pack-row[open]')
    await visible(row.locator('.detail-section p'));assert.equal(await row.count(),1)
    assert.equal(await row.locator('summary .pack-number').innerText(),header.cards[0].number)
    if(!actual)assert.equal(await row.getByRole('link',{name:'참고 인쇄본'}).getAttribute('href'),'https://example.invalid/references/name')
    await noOverflow();await shot('pack-detail')
    await row.getByRole('button',{name:'카드 정보 PNG'}).click()
    const preview=page.locator('.pack-save[open]')
    await preview.getByRole('combobox').selectOption('360')
    await preview.getByRole('button',{name:'이미지 만들기'}).click()
    const single=await save(preview.getByRole('button',{name:'PNG 파일 다운로드'}));assert.equal(single.readUInt32BE(16),360);assert.ok(await colorPixels(single)>1000)
    await preview.getByRole('button',{name:'닫기'}).click()
    await page.getByRole('button',{name:'카드 배열',exact:true}).click()
    const gallery=page.locator('.pack-gallery[open]')
    assert.equal(await gallery.locator('.pack-tile').count(),45)
    const atlas=gallery.locator('span.lib-thumbnail').first()
    const style=await atlas.evaluate(el=>({size:getComputedStyle(el).backgroundSize,box:el.getBoundingClientRect().toJSON()}))
    assert.equal(style.size,'400% 300%','a cold visit must show one full cell of the 4×3 atlas')
    assert.ok(style.box.width>=44 && style.box.height>style.box.width)
    assert.equal(await gallery.locator('.pack-tiles').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),width===360?5:10)
    const labels=gallery.getByRole('checkbox',{name:'카드명 표시'})
    await labels.check();assert.equal(await gallery.locator('.tile-caption strong').first().innerText(),header.cards[0].name)
    await labels.uncheck()
    const field=(idx)=>gallery.locator('fieldset').nth(idx)
    await field(0).getByText('신규',{exact:true}).click()
    await field(0).getByText('재록',{exact:true}).click()
    assert.equal(await gallery.locator('.pack-tile').count(),45)
    const selectedType=header.cards[0].type, selectedRarity=header.cards[0].rarities[0]
    await field(1).getByText(selectedType,{exact:true}).click()
    await field(2).getByText(selectedRarity,{exact:true}).click()
    assert.equal(await gallery.locator('.pack-tile').count(),header.cards.filter(c=>c.type===selectedType && c.rarities.includes(selectedRarity)).length)
    await shot('pack-gallery');await gallery.getByRole('button',{name:'배열 PNG 저장'}).click()
    const galleryFile=await save(preview.getByRole('button',{name:'PNG 파일 다운로드'}));assert.equal(galleryFile.readUInt32BE(16),720);assert.ok(await colorPixels(galleryFile)>1000)
    await preview.getByRole('button',{name:'닫기'}).click()
    await gallery.getByRole('button',{name:'필터 지우기'}).click()
    await gallery.locator('.pack-tile').last().click()
    await visible(row.locator('.details-body article'));assert.equal(await row.locator('.pack-number').innerText(),header.cards[44].number)
    await page.getByRole('button',{name:'카드 배열',exact:true}).click()
    await page.keyboard.press('Escape');assert.equal(await gallery.count(),0);await noOverflow()
    await page.locator('.pack-back').click();await page.waitForURL(u=>u.pathname==='/releases')
    await page.goto(origin+'/shared/decks/fixture')
    const recipe=page.locator('.recipe-panel');await visible(recipe.locator('.lib-recipe'))
    assert.equal(await recipe.locator('.lib-recipe .lib-thumbnail').count(),4)
    await recipe.getByRole('button',{name:'이미지 숨기기'}).click();assert.equal(await recipe.locator('.lib-recipe .lib-thumbnail').count(),0)
    await recipe.getByRole('button',{name:'배열',exact:true}).click();assert.equal(await recipe.locator('.recipe-tiles li').count(),7)
    await visible(recipe.locator('.recipe-counts').getByText('융합 1'))
    await recipe.getByRole('searchbox').fill('DECK-01');assert.equal(await recipe.locator('.recipe-tiles li').count(),2)
    await recipe.getByRole('searchbox').fill('');await shot('deck-gallery')
    const whole=await save(recipe.getByRole('button',{name:'PNG 저장',exact:true}))
    await recipe.getByRole('checkbox',{name:'이미지에 사이드 제외'}).check()
    await recipe.getByRole('button',{name:'이미지 미리보기'}).click()
    const minus=await save(preview.getByRole('button',{name:'PNG 파일 다운로드'}))
    assert.ok(minus.readUInt32BE(20)<whole.readUInt32BE(20));assert.equal(minus.readUInt32BE(16),960)
    await preview.getByRole('button',{name:'닫기'}).click()
    await page.locator('.locale-switch select').selectOption('ja');await visible(recipe.getByRole('heading',{name:'テストデッキ'}))
    await page.locator('.locale-switch select').selectOption('en');await visible(recipe.getByRole('heading',{name:'Fixture deck'}))
    await page.goto(origin+'/shared/decks/large');await recipe.getByRole('button',{name:'Gallery',exact:true}).click()
    assert.equal(await recipe.locator('.recipe-tiles li').count(),72)
    await recipe.getByRole('button',{name:/Show more/}).click();assert.equal(await recipe.locator('.recipe-tiles li').count(),144)
    await noOverflow();assert.deepEqual(errors,[]);await ctx.close()
    console.log(width+'px passed: pack accordion, source card, three gallery filters, card + gallery PNG, jump + Escape, sections/copies, list/gallery/search, side-excluded PNG, preview, and 999-copy pagination.')
  }
}finally{await browser.close()}
