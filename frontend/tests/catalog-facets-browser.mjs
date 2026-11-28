import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile,mkdir} from 'node:fs/promises'
import {extname,resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
const dist=fileURLToPath(new URL('../dist/',import.meta.url)),origin='http://127.0.0.1:19576'
const {chromium}=createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE||'playwright')
const games=[
  ['YUGIOH','유희왕','attribute','DARK','어둠'],['POKEMON','포켓몬 TCG','energyType','Water','물'],
  ['WEISS','바이스 슈발츠','type','Climax','클라이맥스'],['ONEPIECE','원피스 카드 게임','traits','이스트 블루','이스트 블루'],
  ['NIVEL','니벨아레나','type','유닛','유닛'],['RIFTBOUND','리프트바운드','domain','Calm','평정'],
]
const wiki={title:'검증용 컬렉션',language:'ko',url:'https://namu.wiki/w/검증용%20컬렉션',facts:{printingNumber:'002/060',hp:60},
  verificationUrl:'https://pokemoncard.co.kr/cards/detail/TEST002',snapshotDate:'2021-03-01'}
const reading={english:'Kurumi',korean:'쿠루미',title:'토키사키 쿠루미',url:'https://namu.wiki/w/토키사키%20쿠루미',basis:'CHARACTER_READING'}
const englishOnly={id:120,gameCode:'WEISS',number:'WS-EN-120',name:'Untranslated name',language:'en',
  effect:'Original printed effect',effectLanguage:'en',imageUrl:null,variants:[],specs:{language:'en',characterNameReferences:[reading]}}
const cards=games.map(([game,name],i)=>({id:100+i,name:name+' 카드',number:'TEST-'+i,gameCode:game,language:'ko',effect:'확인할 한국어 효과',
  effectLanguage:'ko',releaseDate:i%2?'2020-01-03':null,productReleaseDate:'2020-01-01',
  imageUrl:'https://publisher.example.invalid/uncached/'+i+'.webp',imageLanguage:'ko',
  ...(game==='WEISS'?{nameBasis:'MACHINE_TRANSLATION',effectBasis:'MACHINE_TRANSLATION',nameReferenceUrl:'https://example.invalid/original'}:{}),
  ...(game==='NIVEL'?{nameBasis:'CURATED_TRANSLATION',effectBasis:'CURATED_TRANSLATION'}:{}),
  variants:[],specs:game==='POKEMON'?{wikiReferences:[wiki]}:game==='WEISS'?{readingOriginal:{language:'en',name:'Saved original',effect:'Original rules text'}}:
    game==='ONEPIECE'?{productCode:'OP-15',regionalFacts:{ko:{productCode:'OP-15',sourceUrl:'https://onepiece-cardgame.kr/cardlist/info.php?no=1',attribute:'참격',traits:['이스트 블루','클리크 해적단']}}}:{}}))
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined})
try{
  for(const width of [360,1280]){
    const ctx=await browser.newContext({viewport:{width,height:800},isMobile:width===360,hasTouch:width===360,serviceWorkers:'block'})
    const page=await ctx.newPage(),errors=[],requests=[],hotlinks=[]
    page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(8000)
    await ctx.route('**/*',async route=>{
      const u=new URL(route.request().url()),path=u.pathname,p=u.searchParams
      if(u.origin!==origin){if(u.hostname==='publisher.example.invalid')hotlinks.push(u.href);return route.abort()}
      if(path.startsWith('/api/')){
        requests.push(u);const g=games.find(([code])=>code===p.get('game'))
        const json=data=>route.fulfill({json:data})
        if(path.endsWith('/auth/refresh'))return route.fulfill({status:401,body:'{}'})
        if(path.endsWith('/auth/admin-mode'))return json({mode:'DISABLED'})
        if(path.endsWith('/games'))return json(games.map(([code])=>({code})))
        if(path.endsWith('/packs'))return json([])
        if(path.endsWith('/cards/facets'))return json({years:[2020],traitKeys:g?[g[2]]:[],values:g && p.get('traitKey')===g[2]?[g[3]]:[]})
        if(path.endsWith('/cards') && p.get('q')===englishOnly.number)return json({items:[englishOnly],total:1})
        if(path.endsWith('/cards/'+englishOnly.id))return json(englishOnly)
        if(path.endsWith('/cards')){const items=cards.filter(c=>p.get('withImage')!=='true' && (!g||g[0]===c.gameCode) && (!p.has('traitKey') || g[2]===p.get('traitKey') && g[3]===p.get('traitValue')))
          return json({items,total:items.length})}
        if(/\/cards\/\d+$/.test(path))return json(cards.find(c=>String(c.id)===path.split('/').pop()))
        return route.fulfill({status:404,body:'{}'})
      }
      const file=extname(path)?path.slice(1):'index.html'
      return route.fulfill({body:await readFile(resolve(dist,file)),contentType:({'.js':'text/javascript','.html':'text/html;charset=utf-8','.css':'text/css','.png':'image/png'})[extname(file)]})
    })
    await page.goto(origin+'/?lang=ko');await page.locator('.catalog-entry').first().waitFor()
    assert.equal(requests.filter(u=>u.pathname.endsWith('/facets')).length,0)
    assert.equal(requests.filter(u=>/\/cards\/\d+$/.test(u.pathname)).length,0)
    assert.ok(requests.some(u=>u.pathname.endsWith('/cards') && u.searchParams.get('order')==='edition'))
    for(const [i,[game,name,key,raw,label]] of games.entries()){
      const card=cards[i];await page.locator('.catalog-games').getByRole('button',{name,exact:true}).click()
      const link=page.locator('.catalog-open').getByText('상세',{exact:false}).first()
      await page.waitForURL(u=>u.searchParams.get('game')===game && !u.searchParams.has('traitValue') && !u.searchParams.has('releaseYear'))
      const tray=page.locator('#extra-filters')
      if(!await tray.isVisible())await page.getByRole('button',{name:'필터',exact:true}).click()
      await tray.getByLabel('발매 연도').selectOption('2020')
      await tray.getByLabel('카드 특성').selectOption(key)
      await tray.getByLabel('특성 값').selectOption({label})
      await tray.getByRole('button',{name:'필터 적용'}).click()
      await page.waitForURL(u=>u.searchParams.get('traitKey')===key && u.searchParams.get('traitValue')===raw && u.searchParams.get('releaseYear')==='2020')
      await page.locator('.catalog-entry .card-title time').waitFor()
      await page.locator('.catalog-entry .empty-art').first().waitFor()
      assert.equal(await page.locator('.catalog-entry .card-title time').getAttribute('datetime'),card.releaseDate || card.productReleaseDate)
      assert.ok(requests.some(u=>u.pathname.endsWith('/cards') && u.searchParams.get('game')===game && u.searchParams.get('releaseYear')==='2020' && u.searchParams.get('traitValue')===raw))
      if(game==='RIFTBOUND' && process.env.QA_SCREENSHOTS){await mkdir(process.env.QA_SCREENSHOTS,{recursive:true});await page.screenshot({path:resolve(process.env.QA_SCREENSHOTS,'filters-'+width+'.png')})}
      await link.focus();await link.press('Enter');await page.locator('.card-reader h1').getByText(card.name,{exact:true}).waitFor()
      assert.equal(new URL(page.url()).pathname,'/cards/'+card.id)
      await page.locator('.reader-facts').getByText(card.releaseDate?'발매일':'수록 상품 첫 발매일',{exact:true}).waitFor()
      if(game==='WEISS'){
        assert.equal(await page.locator('.card-reader .card-text-credit').filter({hasText:'자동 번역'}).count(),2)
        assert.equal(await page.getByText('Original rules text',{exact:true}).count(),0)
        await page.locator('.reader-source summary').click()
        await page.locator('.reader-source p[lang=en]').getByText('Original rules text',{exact:true}).waitFor()
      }
      if(game==='POKEMON'){
        await page.locator('.reader-source summary').click()
        await page.locator('.wiki-facts').getByText('002/060',{exact:true}).waitFor()
        assert.equal(await page.getByRole('link',{name:'공식 카드 대조'}).getAttribute('href'),wiki.verificationUrl)
      }
      if(game==='ONEPIECE'){
        await page.locator('.reader-facts').getByText('이스트 블루 · 클리크 해적단',{exact:true}).waitFor()
        await page.locator('.reader-facts').getByText('참격',{exact:true}).waitFor()
        await page.locator('.reader-source summary').click()
        assert.equal(await page.getByRole('link',{name:/한국판 카드 정보/}).getAttribute('href'),card.specs.regionalFacts.ko.sourceUrl)
      }
      if(game==='NIVEL'){
        assert.equal(await page.locator('.card-reader .card-text-credit').filter({hasText:'검수한 번역'}).count(),2)
        assert.equal(await page.locator('.card-reader').getByText('자동 번역',{exact:true}).count(),0)
      }
      await page.locator('.standalone .back-link').click()
      await page.locator('.catalog-entry').first().waitFor()
      assert.equal(await tray.getByLabel('특성 값').inputValue(),raw)
      assert.equal(await tray.getByLabel('발매 연도').inputValue(),'2020')
      const listRequests=()=>requests.filter(u=>u.pathname.endsWith('/cards')).length
      const before=listRequests()
      await page.getByRole('button',{name:'배열',exact:true}).click()
      const tile=page.locator('.catalog-gallery a').first()
      await tile.waitFor()
      assert.equal(listRequests(),before)
      assert.match(await tile.innerText(),new RegExp(card.number))
      await tile.click()
      await page.locator('.standalone .back-link').click()
      await tile.waitFor()
      assert.equal(new URL(page.url()).searchParams.get('view'),'gallery')
      await page.getByLabel('사진 있는 카드').check()
      await page.getByText('검색 조건에 맞는 카드가 없습니다.',{exact:true}).waitFor()
      assert.ok(requests.some(u=>u.searchParams.get('withImage')==='true' && u.searchParams.get('game')===game && u.searchParams.get('traitValue')===raw))
      await page.getByLabel('사진 있는 카드').uncheck()
      await tile.waitFor()
      await page.getByRole('button',{name:'목록',exact:true}).click()
      await page.locator('.catalog-entry').first().waitFor()
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
    }
    await page.goto(origin+'/?lang=ko&q='+englishOnly.number)
    const row=page.locator('.card-row summary')
    await row.getByText('이 언어의 카드명 미등록').waitFor()
    await row.getByText('이미지 미등록',{exact:true}).waitFor()
    assert.equal(await row.locator('strong').innerText(),englishOnly.number)
    assert.ok(!(await row.innerText()).includes(englishOnly.name))
    await row.click()
    assert.equal(await page.getByText('등장인물의 한글 표기').count(),0)
    await page.locator('.reader-source summary').click()
    await page.locator('.reader-source p[lang=en]').getByText(englishOnly.name,{exact:true}).waitFor()
    const ref=page.locator('.reader-source .character-readings')
    assert.equal(await ref.locator('span[lang=en]').innerText(),'Kurumi')
    assert.equal(await ref.getByRole('link',{name:'나무위키 · 토키사키 쿠루미'}).getAttribute('href'),new URL(reading.url).href)
    assert.equal(await page.locator('.reader-title h3').innerText(),englishOnly.number)
    for(const lang of ['en','ja']){
      await page.goto(origin+'/cards/'+englishOnly.id+'?lang='+lang)
      await page.locator('.reader-source summary').click()
      assert.equal(await page.locator('.character-readings').count(),0)
      assert.ok(!(await page.locator('.reader-source').innerText()).includes('쿠루미'))
    }
    assert.deepEqual(errors,[]);assert.deepEqual(hotlinks,[]);await ctx.close()
    console.log(width+'px: six game-specific exact-value filters, year, direct detail, print and set dates, Korean labels, wiki facts, machine translation and restored results passed.')
  }
}finally{await browser.close()}
