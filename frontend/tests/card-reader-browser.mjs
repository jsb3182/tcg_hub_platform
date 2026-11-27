// Run against an isolated Spring instance containing the original DBGV pack, after building Vue.
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {mkdir,readFile} from 'node:fs/promises'
import {extname,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const origin=process.env.CARD_READER_ORIGIN
if(!origin || new URL(origin).hostname!=='127.0.0.1')throw new Error('Set CARD_READER_ORIGIN to the loopback DBGV QA server')
const dist=fileURLToPath(new URL('../dist/',import.meta.url))
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || undefined})
const mime={'.html':'text/html;charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'}
try {
  for(const width of [360,1280]){
    const ctx=await browser.newContext({viewport:{width,height:800},isMobile:width===360,hasTouch:width===360,serviceWorkers:'block'})
    const get=async path=>{const res=await ctx.request.get(origin+'/api/v1/'+path);assert.ok(res.ok(),path);return res.json()}
    const sets=await get('releases'), header=sets.find(set=>set.code==='DBGV')
    const printings=await get('packs/'+header.id+'?lang=ko'), first=printings.cards.find(c=>c.number==='DBGV-JP001'), incomplete=printings.cards.find(c=>c.number==='DBGV-JP027')
    assert.ok(first && incomplete)
    const page=await ctx.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message))
    await ctx.route('**/*',async route=>{
      const u=new URL(route.request().url())
      if(u.origin!==origin)return route.abort()
      if(!process.env.READER_LOCAL_DIST || /^\/(api|media)\//.test(u.pathname))return route.continue()
      const file=extname(u.pathname)?u.pathname.slice(1):'index.html'
      return route.fulfill({body:await readFile(resolve(dist,file)),contentType:mime[extname(file)]})
    })
    const snap=async(label,element)=>{
      if(!process.env.QA_SCREENSHOTS)return
      await mkdir(process.env.QA_SCREENSHOTS,{recursive:true})
      await element.evaluate(el=>window.scrollTo(0,Math.max(0,window.scrollY+el.getBoundingClientRect().top-72)))
      await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,label+'-'+width+'.png')})
    }
    const check=async (row,lang,card)=>{
      const reader=row.locator('.card-reader')
      await reader.locator('.reader-title :is(h1,h3)').getByText(card.name,{exact:true}).waitFor()
      assert.equal(await reader.locator('.reader-number').innerText(),card.number)
      assert.equal(await reader.locator('.detail-section p').getAttribute('lang'),lang)
      assert.equal(await reader.locator('.detail-section p').textContent(),card.effect)
      const art=reader.locator('button.atlas')
      await art.waitFor()
      const tile=card.variants.find(v=>v.image?.language==='ja').image
      assert.ok((await art.evaluate(el=>el.style.backgroundImage)).includes(tile.url))
      const sheet=await ctx.request.get(origin+tile.url);assert.ok(sheet.ok() && (await sheet.body()).length>1000)
      assert.equal(await reader.locator('.edition-note').innerText(),({ko:'일본어판',en:'Japanese edition',ja:'カード画像 · 日本語版'})[lang])
      assert.equal(await row.locator('.reader-source').getAttribute('open'),null)
      assert.ok((await reader.locator('.reader-stats').innerText()).includes('1000'))
      const imageBox=await art.boundingBox(),factsBox=await reader.locator('.reader-facts').boundingBox()
      assert.ok(imageBox.x+imageBox.width<=factsBox.x && imageBox.height>imageBox.width)
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
      await snap('DBGV-JP001-'+lang,reader)
    }
    for(const lang of ['ko','en','ja']){
      const card=await get('cards/'+first.id+'?lang='+lang)
      assert.equal(card.language,lang);assert.equal(card.effectLanguage,lang)
      await page.goto(origin+'/cards/'+card.id+'?lang='+lang)
      await check(page,lang,card)
    }
    await page.goto(origin+'/releases/'+header.id+'?lang=ko')
    const row=page.locator('.pack-row[open]')
    await check(row,'ko',await get('cards/'+first.id+'?lang=ko'))
    await row.getByRole('button',{name:'카드 정보 PNG'}).click()
    const preview=page.locator('.pack-save[open]');await preview.getByRole('combobox').selectOption('360')
    await preview.getByRole('button',{name:'이미지 만들기'}).click()
    const download=page.waitForEvent('download');await preview.getByRole('button',{name:'PNG 파일 다운로드'}).click()
    const parts=[];for await(const part of await (await download).createReadStream())parts.push(part)
    const png=Buffer.concat(parts);assert.equal(png.subarray(1,4).toString(),'PNG');assert.equal(png.readUInt32BE(16),360)
    assert.ok(png.length>10000)
    const raw=await get('cards/'+incomplete.id+'?lang=en');assert.notEqual(raw.language,'en');assert.notEqual(raw.effectLanguage,'en')
    await page.goto(origin+'/cards/'+incomplete.id+'?lang=en')
    const reader=page.locator('.card-reader');await reader.getByRole('heading',{name:raw.number}).waitFor()
    await reader.getByText('No effect text in this language').waitFor()
    assert.ok(!(await reader.innerText()).includes(raw.name) && !(await reader.innerText()).includes(raw.effect))
    await snap('unavailable-en',reader)
    const source=page.locator('.reader-source');await source.locator('summary').click();await source.getByText(raw.effect,{exact:true}).waitFor()
    await page.goto(origin+'/?'+new URLSearchParams({game:'YUGIOH',q:raw.number,lang:'en'}))
    const result=page.locator('.catalog-list .card-row').filter({has:page.locator('.card-code').getByText(raw.number,{exact:true})}).first()
    await result.locator(':scope>summary').click()
    await result.locator('.card-reader').getByRole('heading',{name:raw.number}).waitFor()
    assert.ok(!(await result.locator(':scope>summary').innerText()).includes(raw.name),'An open catalog row must also use the selected language')
    await page.goto(origin+'/releases/'+header.id+'?lang=en')
    const packRow=page.locator('#pack-card-'+incomplete.id)
    await packRow.locator(':scope>summary').click()
    await packRow.locator('.card-reader').getByRole('heading',{name:raw.number}).waitFor()
    assert.ok(!(await packRow.locator(':scope>summary').innerText()).includes(raw.name))
    assert.deepEqual(errors,[])
    console.log(width+'px Spring card reader: DBGV-JP001 KO/EN/JA full text, correct Japanese physical tile, isolated sources, PNG '+png.length+' bytes; DBGV-JP027 missing English text checked.')
    await ctx.close()
  }
} finally {await browser.close()}
