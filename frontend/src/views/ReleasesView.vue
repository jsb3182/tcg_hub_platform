<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {mediaPath,request,sourceLink} from '../api'
import {gameCodes,gameName,locale} from '../i18n'
import {packTitle,pt,regionName,releaseName,releaseRegions} from '../pack'
import {bookmarkedPack,publicPacks} from '../legacyPacks'
import {selectedCodes,toggledCode,releaseDistance,kstMonth,changeMonth,productTypes} from '../releaseCalendar'
import ReleaseMonthGrid from '../components/ReleaseMonthGrid.vue'
import PersonalCalendar from '../components/PersonalCalendar.vue'
import PublicPackFinder from '../components/PublicPackFinder.vue'

const route=useRoute(),router=useRouter(),size=24
const periods={upcoming:'발매 예정',past:'지난 발매',all:'날짜 전체'}
const sections=[['SCHEDULE','팩 발매 일정'],['DISTRIBUTION','동봉 · 배포 카드'],['PREMIERE','TCG 월드 프리미어 카드'],['ARCHIVE','장기 미수록 카드']]
const games=computed(()=>selectedCodes(route.query.game,gameCodes))
const regions=computed(()=>selectedCodes(route.query.region,Object.keys(releaseRegions)))
const types=computed(()=>selectedCodes(route.query.productType,Object.keys(productTypes)))
const game=computed(()=>games.value.join(',')),region=computed(()=>regions.value.join(','))
const products=computed(()=>types.value.join(','))
const grid=computed(()=>route.query.view==='month')
const asOf=ref('')
const month=computed(()=>/^\d{4}-(0[1-9]|1[0-2])$/.test(route.query.month||'') ? route.query.month : kstMonth(asOf.value))
const requestedMonth=computed(()=>grid.value ? month.value : '')
const day=computed(()=>typeof route.query.day==='string' && route.query.day.startsWith(month.value+'-')?route.query.day:'')
const period=computed(()=>Object.keys(periods).includes(route.query.period)?route.query.period:'upcoming')
const query=computed(()=>typeof route.query.q==='string'?route.query.q.slice(0,100):'')
const page=computed(()=>/^\d{1,6}$/.test(route.query.page||'')?Number(route.query.page):0)
const draft=ref(query.value),result=ref(null),packs=ref(null),loading=ref(true),error=ref(''),retry=ref(0),limits=ref({})
const resultsHeading=ref(),jumpAfterPage=ref(false)
const packError=ref(''),packRetry=ref(0)

function destination(edits){
  const params={...route.query,...edits}
  for(const key of Object.keys(params))if(params[key]===''||params[key]==null)delete params[key]
  return {name:'releases',query:params}
}
function filter(edits){return router.replace(destination({q:draft.value.trim(),page:null,day:null,...edits}))}
watch(query,value=>{draft.value=value})
watch(draft,(value,_,cleanup)=>{
  if(value.trim()===query.value)return
  const timer=setTimeout(()=>filter({q:value.trim()}),220)
  cleanup(()=>clearTimeout(timer))
})
function turn(n){jumpAfterPage.value=true;return router.push(destination({page:n||null}))}
watch([game,query],()=>{limits.value={}})
watch(packRetry,async(_,__,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  packError.value=''
  try{const data=await publicPacks();if(!abort.signal.aborted)packs.value=data}
  catch(cause){if(!abort.signal.aborted)packError.value=cause.message}
},{immediate:true})
watch([()=>route.hash,packs],async([hash,rows])=>{
  if(hash.startsWith('#pack-')){
    const pack=bookmarkedPack(rows,hash)
    if(pack)await router.replace({name:'pack',params:{id:pack.id},query:route.query})
    return
  }
  if(!sections.some(([id])=>hash==='#release-'+id))return
  await nextTick();document.getElementById(hash.slice(1))?.scrollIntoView({block:'start'})
},{immediate:true})
watch([game,region,period,query,page,retry,grid,requestedMonth,products],async([g,r,when,q,n,_,calendar,m,product],previous,cleanup)=>{
  const controller=new AbortController(),signal=controller.signal
  cleanup(()=>controller.abort())
  error.value='';loading.value=true;result.value=null
  try{
    const params=new URLSearchParams({period:when,page:calendar?0:n,size:calendar?100:size})
    if(g)params.set('game',g)
    if(r)params.set('region',r)
    if(q)params.set('q',q)
    if(product)params.set('productType',product)
    if(calendar)params.set('month',m)
    const data=await request('/release-calendar?'+params,{signal})
    if(signal.aborted)return
    if(calendar){
      let p=0
      while(data.items.length<data.total && data.items.length>0){
        params.set('page',String(++p))
        const chunk=await request('/release-calendar?'+params,{signal})
        if(signal.aborted)return
        if(!chunk.items.length)break
        data.items.push(...chunk.items)
      }
    }
    asOf.value=data.asOf
    const last=Math.max(0,Math.ceil(data.total/size)-1)
    if(!calendar && n>last){await router.replace(destination({page:last||null}));return}
    result.value=data
  }catch(cause){if(!signal.aborted)error.value=cause.message}
  finally{
    if(!signal.aborted){
      loading.value=false
      if(jumpAfterPage.value){
        jumpAfterPage.value=false;await nextTick()
        resultsHeading.value?.focus({preventScroll:true});resultsHeading.value?.scrollIntoView({block:'start'})
      }
    }
  }
},{immediate:true})

const months=computed(()=>{
  const dates=new Map()
  const format=new Intl.DateTimeFormat(locale.value,{year:'numeric',month:'long',timeZone:'UTC'})
  for(const event of result.value?.items||[]){
    if(grid.value && day.value && day.value!==event.releaseDate)continue
    const month=event.releaseDate.slice(0,7)
    if(!dates.has(month))dates.set(month,{id:month,title:format.format(new Date(month+'-01T00:00:00Z')),items:[]})
    dates.get(month).items.push(event)
  }
  return [...dates.values()]
})
const groups=computed(()=>{
  const term=query.value.trim().normalize('NFKC').toLocaleLowerCase()
  const matching=(packs.value||[]).filter(p=>(!games.value.length||games.value.includes(p.gameCode)) &&
    [p.name,p.officialProduct?.englishName,p.code,p.latestProduct,p.metadata?.kind].some(v=>String(v||'').normalize('NFKC').toLocaleLowerCase().includes(term)))
  return sections.map(([id,title])=>{
    const items=matching.filter(p=>p.group===id)
    if(id==='PREMIERE')items.sort((a,b)=>(a.officialProduct?.launchDate||a.releaseDate||'9999').localeCompare(b.officialProduct?.launchDate||b.releaseDate||'9999'))
    return {id,title,items:items.slice(0,limits.value[id]||16),total:items.length}
  }).filter(s=>s.total)
})
function range(p){return [...new Set([p.firstProductDate,p.lastProductDate].filter(Boolean))].join(' – ')}
function packRoute(id,section){return {name:'pack',params:{id},query:section?{...route.query,section}:route.query}}
</script>
<template>
  <div class="releases-page">
    <header class="release-head"><h1>{{ pt('발매 일정') }}</h1>
      <div class="release-filters">
        <label>{{ pt('게임') }}<select :value="game" @change="filter({game:$event.target.value})"><option value="">{{ pt('모든 종목') }}</option><option v-if="games.length>1" :value="game" disabled>{{ games.map(gameName).join(' · ') }}</option>
          <option v-for="code in gameCodes" :key="code" :value="code">{{ gameName(code) }}</option></select></label>
        <label class="release-search">{{ pt('팩 검색') }}<input v-model="draft" type="search" maxlength="100" :placeholder="pt('팩 이름 또는 코드')" @keydown.enter.prevent="filter({})"></label>
      </div>
    </header>
    <PublicPackFinder :game="game"/>
    <PersonalCalendar/>
    <nav v-if="groups.length" class="release-sections" :aria-label="pt('팩 분류')">
      <a v-for="s in groups" :key="s.id" :href="'#release-'+s.id">{{ pt(s.title) }}</a>
      <a href="#regional-calendar" class="calendar-jump">{{ pt('지역별 발매 일정') }} ↓
        <small v-if="groups.length && result?.items?.length">{{ result.items[0].releaseDate }} · {{ releaseName(result.items[0]) }}</small>
      </a>
    </nav>
    <div class="release-layout" :class="{'has-packs':groups.length>0}">
      <p v-if="packError" class="inline-error" role="alert">{{ packError }} <button class="text-button" @click="packRetry++">{{ pt('다시 시도') }}</button></p>
      <div v-if="groups.length" class="pack-sections">
      <section v-for="s in groups" :id="'release-'+s.id" :key="s.id" class="release-section">
        <h2>{{ pt(s.title) }} <small>{{ s.total }}</small></h2>
        <ul><li v-for="p in s.items" :key="p.id"><RouterLink :to="packRoute(p.id,s.id)">
          <div class="release-row-title"><small>{{ [p.code,p.metadata?.kind||gameName(p.gameCode)].filter(Boolean).join(' · ') }}</small><strong>{{ packTitle(p) }}</strong>
            <span v-if="p.group==='DISTRIBUTION'||p.group==='ARCHIVE'">{{ pt('상품 수') }} {{ p.productCount }} <template v-if="range(p)">· {{ range(p) }}</template></span>
            <span v-else-if="p.officialProduct">{{ pt('북미 일반 발매') }} · {{ p.officialProduct.launchDate }}</span>
            <span v-else>{{ [p.metadata?.jp||p.releaseDate,p.metadata?.kr?pt('한국 발매 예상')+' '+p.metadata.kr:!p.releaseDate?p.releaseLabel:''].filter(Boolean).join(' · ') || pt('일정 미정') }}</span>
            <span v-if="p.latestProduct && (p.group==='DISTRIBUTION'||p.group==='ARCHIVE')">{{ pt('최근 상품') }} · {{ p.latestProduct }}</span>
          </div>
          <div class="release-count"><template v-if="p.total||!p.officialProduct"><b>{{ p.total }}</b> {{ pt('수록 카드') }}</template><template v-else>{{ pt('도감 등록 전') }}</template><small v-if="p.newCount">{{ pt('신규') }} {{ p.newCount }}</small></div>
          <img v-if="mediaPath(p.bannerUrl)" :src="mediaPath(p.bannerUrl)" alt="" loading="lazy">
        </RouterLink></li></ul>
        <button v-if="s.total>s.items.length" class="secondary" @click="limits={...limits,[s.id]:s.items.length+24}">{{ pt('더 보기') }} ({{ s.items.length }}/{{ s.total }})</button>
      </section>
      </div>
      <section id="regional-calendar" class="regional-calendar">
        <div class="calendar-heading"><h2>{{ pt('지역별 발매 일정') }}</h2>
          <label>{{ pt('발매 지역') }}<select :value="region" @change="filter({region:$event.target.value})"><option value="">{{ pt('모든 지역') }}</option><option v-if="regions.length>1" :value="region" disabled>{{ regions.map(regionName).join(' · ') }}</option>
            <option v-for="(_,code) in releaseRegions" :key="code" :value="code">{{ regionName(code) }}</option></select></label>
        </div>
    <details class="release-multi"><summary>{{ pt('종목·지역·상품 필터') }}<small v-if="games.length+regions.length+types.length"> ({{ games.length+regions.length+types.length }})</small></summary>
      <fieldset><legend>{{ pt('게임') }}</legend><label v-for="code in gameCodes" :key="code"><input type="checkbox" :checked="games.includes(code)" @change="filter({game:toggledCode(games,code)})">{{ gameName(code) }}</label></fieldset>
      <fieldset><legend>{{ pt('발매 지역') }}</legend><label v-for="(_,code) in releaseRegions" :key="code"><input type="checkbox" :checked="regions.includes(code)" @change="filter({region:toggledCode(regions,code)})">{{ regionName(code) }}</label></fieldset>
      <fieldset><legend>{{ pt('상품 유형') }}</legend><label v-for="(label,code) in productTypes" :key="code"><input type="checkbox" :checked="types.includes(code)" @change="filter({productType:toggledCode(types,code)})">{{ pt(label) }}</label></fieldset>
      <button class="text-button" type="button" @click="filter({game:null,region:null,productType:null})">{{ pt('필터 초기화') }}</button>
    </details>
    <div class="calendar-mode" :aria-label="pt('일정 보기')"><button type="button" :aria-pressed="!grid" @click="filter({view:null,month:null})">{{ pt('타임라인') }}</button>
      <button type="button" :aria-pressed="grid" @click="filter({view:'month',month,period:'all'})">{{ pt('월간 달력') }}</button></div>
    <nav class="release-views" :aria-label="pt('일정 보기')">
      <RouterLink v-for="(label,key) in periods" :key="key" :aria-current="period===key?'page':null"
        :to="destination({period:key,q:draft.trim(),region,page:null,day:null})">{{ pt(label) }}</RouterLink>
    </nav>
    <p v-if="loading" role="status" class="state">{{ pt('불러오는 중…') }}</p>
    <p v-else-if="error" role="alert" class="inline-error">{{ error }} <button type="button" class="text-button" @click="retry++">{{ pt('다시 시도') }}</button></p>
    <template v-else-if="result">
      <div class="release-summary" ref="resultsHeading" tabindex="-1">
        <span role="status">{{ pt('일정') }} <b>{{ result.total.toLocaleString(locale) }}</b></span>
        <small v-if="result.asOf">{{ pt('기준일') }} <time :datetime="result.asOf">{{ result.asOf }}</time></small>
      </div>
      <ReleaseMonthGrid v-if="grid" :month="month" :items="result.items" :as-of="result.asOf" :day="day"
        @select="value=>filter({day:value})" @month="offset=>filter({month:changeMonth(month,offset)})"/>
      <p v-if="!result.total" class="state">{{ pt(period==='upcoming'&&!query?'등록된 발매 예정 일정이 없습니다.':'조건에 맞는 발매 일정이 없습니다.') }}
        <RouterLink v-if="period==='upcoming'" :to="destination({period:'past',page:null})">{{ pt('지난 발매') }} →</RouterLink></p>
      <section v-for="month in months" :key="month.id" class="release-month">
        <h2>{{ month.title }}</h2>
        <ul><li v-for="e in month.items" :key="e.id">
          <time class="release-date" :datetime="e.releaseDate">{{ e.releaseDate }} <small>{{ releaseDistance(e.releaseDate,result.asOf) }}</small></time>
          <div class="event-product">
            <small>{{ [gameName(e.gameCode),regionName(e.region),productTypes[e.productType] && e.productType!=='UNKNOWN'?pt(productTypes[e.productType]):'',e.code].filter(Boolean).join(' · ') }}</small>
            <RouterLink v-if="e.catalogPackId" :to="packRoute(e.catalogPackId)" :aria-label="releaseName(e)+' · '+pt('팩 상세')">
              <span :lang="e.names?.[locale]?locale:undefined">{{ releaseName(e) }}</span> <span class="to-pack" aria-hidden="true">→</span></RouterLink>
            <strong v-else :lang="e.names?.[locale]?locale:undefined">{{ releaseName(e) }}</strong>
          </div>
          <div class="event-links"><small v-if="e.catalogPackId && e.catalogCount>0">{{ pt('수록 카드') }} {{ e.catalogCount.toLocaleString(locale) }}</small>
            <a v-if="sourceLink(e.sourceUrl)" :href="sourceLink(e.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ pt('발매 정보 출처') }} <span aria-hidden="true">↗</span></a>
          </div>
        </li></ul>
      </section>
      <nav v-if="!grid && result.total>size" class="pagination" :aria-label="pt('결과 페이지')">
        <button class="secondary" :disabled="!page" @click="turn(page-1)">{{ pt('이전') }}</button>
        <span>{{ page+1 }} / {{ Math.ceil(result.total/size) }}</span>
        <button class="secondary" :disabled="(page+1)*size>=result.total" @click="turn(page+1)">{{ pt('다음') }}</button>
      </nav>
    </template>
      </section>
    </div>
  </div>
</template>
<style scoped>
.release-multi{margin:.55rem 0;border-block:1px solid var(--bd)}.release-multi summary{cursor:pointer;padding:.65rem 0;min-height:44px;font-size:.88rem;font-weight:600}
.release-multi fieldset{border:0;padding:0;margin:3px 0 9px}.release-multi legend{font-weight:600;font-size:.84rem;color:var(--mu)}.release-multi label{display:inline-flex;align-items:center;gap:4px;padding:4px 10px 4px 0;min-height:36px;font-size:.85rem}.release-multi input{accent-color:var(--ac)}
.calendar-mode{display:flex;gap:4px;margin:.7rem 0}.calendar-mode button{background:var(--sf);color:var(--mu);border:1px solid var(--bd);border-radius:5px;padding:.4rem .7rem;min-height:40px}.calendar-mode button[aria-pressed=true]{color:var(--ac);border-color:var(--ac)}
.release-date small{white-space:nowrap}
.releases-page{max-width:62rem;margin:2rem auto}.release-head h1{margin:0 0 1.15rem}.release-filters{display:grid;grid-template-columns:minmax(8rem,1fr) minmax(10rem,2.2fr);gap:.6rem 1rem}
.release-filters label,.calendar-heading label{display:grid;gap:.25rem;min-width:0;color:var(--mu);font-size:.85rem}.release-filters :is(input,select),.calendar-heading select{width:100%;min-width:0;min-height:44px;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:6px;padding:.45rem .65rem}
.release-views,.release-sections{display:flex;align-items:center;flex-wrap:wrap;gap:0 1.15rem;border-bottom:1px solid var(--bd);margin-top:1rem}
.release-layout>*,.calendar-jump{min-width:0}.regional-calendar{margin-top:1.6rem;scroll-margin-top:5rem}.calendar-heading{display:flex;align-items:end;justify-content:space-between;gap:.6rem;flex-wrap:wrap}.calendar-heading>h2{font-size:1.25rem;margin:0}.calendar-heading label{max-width:min(12rem,100%)}.regional-calendar .release-views{margin-top:.3rem}.calendar-jump small{display:none}
@media(min-width:840px){
 .release-layout.has-packs{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);column-gap:2rem}
 .has-packs .regional-calendar{align-self:start;border-inline-start:1px solid var(--bd);padding-inline-start:1.5rem}
 .has-packs .release-month li{grid-template-columns:minmax(0,1fr) auto;gap:.1rem .5rem}
 .has-packs .release-date{grid-area:1/1;font-size:.82rem}.has-packs .event-product{grid-area:2/1/3/3}.has-packs .event-links{grid-area:1/2}.has-packs .event-links small{display:none}
}
@media(max-width:839px){
 .calendar-jump{width:100%;gap:.6rem}.calendar-jump small{display:block;min-width:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}
.release-views a,.release-sections a{display:inline-flex;align-items:center;min-height:44px;text-decoration:none;text-underline-offset:.25em}.release-views a{border-bottom:2px solid transparent;color:var(--mu)}.release-views a[aria-current=page]{color:var(--ac);border-bottom-color:var(--ac);font-weight:700}.release-views a:hover,.release-sections a:hover{text-decoration:underline}
.release-summary{display:flex;justify-content:space-between;align-items:center;gap:.6rem;margin:1.25rem 0;color:var(--mu);scroll-margin-top:5rem}.release-summary b{color:var(--tx)}
.release-month,.release-section{margin:1.6rem 0 2.2rem;scroll-margin-top:6rem}.release-month h2,.release-section h2{font-size:1.25rem;margin:0 0 .35rem}
.releases-page ul{list-style:none;margin:0;padding:0}.release-month li,.release-section li{border-bottom:1px solid var(--bd)}
.release-month li{display:grid;grid-template-columns:7.5rem minmax(0,1fr) auto;align-items:center;gap:.25rem 1rem;padding:.7rem 0}
.release-date,.release-count,.release-summary time{font-variant-numeric:tabular-nums}.release-date{font-size:.94rem}
.event-product,.event-links,.release-row-title{display:grid;min-width:0;gap:.16rem;overflow-wrap:anywhere}.event-product>a,.event-product>strong,.release-row-title strong{color:var(--tx);font-size:1.02rem;font-weight:650;text-decoration:none}.event-product>a:hover{text-decoration:underline}
.event-product>a{display:block;width:fit-content;min-height:32px}.to-pack{color:var(--ac);white-space:nowrap}
.event-links{justify-items:end}.event-links a{display:inline-flex;align-items:center;gap:.2rem;min-height:36px;font-size:.84rem;text-underline-offset:.2rem}.releases-page small,.release-row-title span{color:var(--mu);font-size:.82rem}
.release-section li>a{display:flex;align-items:center;gap:1rem;min-height:76px;padding:.75rem 0;text-decoration:none;color:var(--tx)}.release-row-title{flex:1}.release-section li>a:hover strong{text-decoration:underline}.release-count{text-align:end;font-size:.78rem}.release-count b{color:var(--ac)}.release-count small{display:block}.release-section img{width:5.75rem;height:3.25rem;object-fit:cover;border-radius:4px}.release-section>button{margin-top:.8rem}
@media(max-width:650px){
 .releases-page{margin:1.3rem auto}.release-filters{grid-template-columns:minmax(0,.9fr) minmax(0,1.3fr);gap:.55rem}
 .release-views{gap:0 .8rem}.release-views a{font-size:.88rem}.release-month li{grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:.2rem .5rem}
 .release-date{grid-area:1/1;color:var(--mu);font-size:.82rem}.event-product{grid-area:2/1/3/3}.event-links{grid-area:1/2;display:flex;align-items:baseline;gap:.45rem}.event-links small{display:none}
 .release-section img{width:3.25rem;height:2.9rem}.release-count{max-width:4.4rem}.release-section li>a{gap:.55rem}
}
</style>
