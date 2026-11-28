<script setup>
import { computed, defineAsyncComponent, nextTick, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { mediaPath, request, sourceLink } from '../api'
import { gameName, locale } from '../i18n'
import { countLabel, facetLabel, inclusions, packTitle, pt, regionName, shortRarity } from '../pack'
import CardTextCredit from '../components/CardTextCredit.vue'
import RiftEffectSummary from '../components/RiftEffectSummary.vue'
import PackGallery from '../components/PackGallery.vue'
import LegacyPackNavigation from '../components/LegacyPackNavigation.vue'

const route=useRoute()
const CardDetails=defineAsyncComponent(()=>import('../components/CardDetails.vue'))
const pack=ref(null), cards=ref([]), expanded=ref(null), page=ref(0), packPage=ref(0)
const visited=reactive(new Set())
const linkedCard=computed(()=>{
  const number=/^#pack-card-([1-9]\d{0,14})$/.exec(route.hash)?.[1]
  return number?Number(number):null
})
const loading=ref(true), moreBusy=ref(false), hasMore=ref(false), error=ref(''), moreError=ref(''), retry=ref(0)
const q=ref(''), inclusion=ref(''), sort=ref('source'),listTop=ref()
const releaseEvents=ref([]), releasePage=ref(0), releaseTotal=ref(0), releaseError=ref(false), releaseBusy=ref(false), releaseRetry=ref(0)
const pageSize=30
const countFields={NEW:'newCount',REPRINT:'reprintCount',NEW_ART:'newArtCount'}
const filtered=computed(()=>{
  const term=q.value.trim().normalize('NFKC').toLocaleLowerCase()
  return cards.value.filter(card=>(!inclusion.value || card.inclusion===inclusion.value) &&
    (!term || [card.name,card.number,card.originalName,card.effect,card.product].some(value=>
      typeof value==='string' && value.normalize('NFKC').toLocaleLowerCase().includes(term))))
})
const pages=computed(()=>Math.ceil(filtered.value.length/pageSize))
const shown=computed(()=>filtered.value.slice(page.value*pageSize,(page.value+1)*pageSize))
const special=computed(()=>pack.value?.group && pack.value.group!=='SCHEDULE')
const showInclusions=computed(()=>pack.value?.gameCode==='YUGIOH'||Object.values(countFields).some(key=>pack.value?.[key]>0))
const otherEvents=computed(()=>{
  const product=pack.value?.officialProduct
  return releaseEvents.value.filter(e=>e.catalogPackId===pack.value?.id &&
    !(e.region==='NA' && e.releaseDate===product?.launchDate && e.sourceUrl===product?.sourceUrl))
})
const productReference=computed(()=>pack.value?.wikiProductReference)
const backTo=computed(()=>{
  const {section,...query}=route.query
  const hash=['catalog-packs','regional-calendar'].includes(section)?'#'+section:['SCHEDULE','DISTRIBUTION','PREMIERE','ARCHIVE'].includes(section)?'#release-'+section:''
  return {name:'releases',query,hash}
})
const announced=computed(()=>{
  const n=pack.value?.officialProduct?.setSize ?? pack.value?.metadata?.cnt
  return /^\d{1,5}$/.test(String(n)) && Number(n)>0?Number(n):null
})
const breakdown=computed(()=>{
  const groups=[new Map(),new Map()]
  for(const card of cards.value){
    const rarities=card.rarities?.length?card.rarities:[card.rarity]
    for(const val of new Set(rarities.filter(Boolean)))groups[0].set(val,(groups[0].get(val)||0)+1)
    if(card.type)groups[1].set(card.type,(groups[1].get(card.type)||0)+1)
  }
  return groups.map(group=>[...group].sort((a,b)=>b[1]-a[1]||String(a[0]).localeCompare(String(b[0]))))
})
let controller, loadToEnd=false
watch(()=>route.params.id,()=>{releasePage.value=0;releaseEvents.value=[];releaseTotal.value=0},{flush:'sync'})
watch([()=>route.params.id,releasePage,releaseRetry],async([id,n],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  releaseError.value=false;releaseBusy.value=true
  try{
    const data=await request('/release-calendar?'+new URLSearchParams({packId:id,period:'all',size:24,page:n}),{signal:abort.signal})
    if(abort.signal.aborted)return
    const rows=data.items||[]
    releaseEvents.value=n?releaseEvents.value.concat(rows):rows
    releaseTotal.value=data.total||0
  }catch{if(!abort.signal.aborted)releaseError.value=true}
  finally{if(!abort.signal.aborted)releaseBusy.value=false}
},{immediate:true})
function apiPage(n,signal){
  return request('/packs/'+encodeURIComponent(route.params.id)+'?'+new URLSearchParams({lang:locale.value,page:n,size:200,sort:sort.value}),{signal})
}
async function loadMore(all=false){
  if(!hasMore.value || !controller) return
  if(all)loadToEnd=true
  if(moreBusy.value)return
  const signal=controller.signal
  moreBusy.value=true;moreError.value=''
  try{
    do{
      const data=await apiPage(packPage.value+1,signal)
      if(signal.aborted) return
      cards.value=cards.value.concat(data.cards);packPage.value=data.page
      hasMore.value=Boolean(data.hasMore && data.cards.length)
    }while(loadToEnd && hasMore.value)
  }catch(e){if(!signal.aborted)moreError.value=e.message}
  finally{if(!signal.aborted){moreBusy.value=false;loadToEnd=false}}
}
watch([()=>route.params.id,locale,retry,sort],async([id],previous,onCleanup)=>{
  const different=previous?.[0]!==id
  const controllerForRequest=new AbortController()
  controller=controllerForRequest
  const signal=controllerForRequest.signal
  onCleanup(()=>controllerForRequest.abort())
  if(different){q.value='';inclusion.value='';expanded.value=null;page.value=0;visited.clear()}
  loading.value=true;error.value='';moreError.value='';moreBusy.value=false;hasMore.value=false;loadToEnd=false
  try{
    const data=await apiPage(0,signal)
    if(signal.aborted)return
    const {cards:rows,...header}=data
    pack.value=header;cards.value=rows;packPage.value=0;hasMore.value=data.hasMore
    if(hasMore.value && (q.value || inclusion.value || page.value>0))await loadMore(true)
  }catch(e){if(!signal.aborted)error.value=e.message}
  finally{if(!signal.aborted)loading.value=false}
},{immediate:true})
watch([q,inclusion],()=>{
  page.value=0;expanded.value=null
  if(hasMore.value)loadMore(true)
})
watch(expanded,id=>{if(id!==null)visited.add(id)},{flush:'sync'})
watch([linkedCard,loading], async ([id,busy],_,cleanup)=>{
  if(!id || busy || error.value)return
  let current=true;cleanup(()=>{current=false})
  if(!cards.value.some(card=>card.id===id) && hasMore.value)await loadMore(true)
  if(current && cards.value.some(card=>card.id===id))await pickCard(id)
})
function toggle(id,event){
  if(event.currentTarget.open)expanded.value=id
  else if(expanded.value===id)expanded.value=null
}
async function goPage(n){
  const signal=controller?.signal
  if(hasMore.value && (n+1)*pageSize>filtered.value.length){
    await loadMore()
    if(signal?.aborted || moreError.value)return
  }
  if(n<0 || n>=pages.value)return
  page.value=n;expanded.value=null
  await nextTick();listTop.value?.focus({preventScroll:true});listTop.value?.scrollIntoView({block:'start'})
}
async function pickCard(id){
  q.value='';inclusion.value=''
  await nextTick()
  const index=cards.value.findIndex(card=>card.id===id)
  if(index<0)return
  page.value=Math.floor(index/pageSize);expanded.value=id
  await nextTick()
  const row=document.getElementById('pack-card-'+id)
  row?.querySelector('summary')?.focus({preventScroll:true});row?.scrollIntoView({block:'start'})
}
</script>
<template>
  <div class="pack-page">
    <RouterLink class="pack-back" :to="backTo"><span aria-hidden="true">←</span>{{ pt('발매 일정') }}</RouterLink>
    <p v-if="loading" class="state" role="status">{{ pt('카드 불러오는 중…') }}</p>
    <div v-else-if="error" class="state" role="alert"><p>{{ error }}</p><button type="button" class="secondary" @click="retry++">{{ pt('다시 시도') }}</button></div>
    <template v-else-if="pack">
      <header class="pack-heading">
        <img v-if="mediaPath(pack.bannerUrl)" class="pack-cover" :src="mediaPath(pack.bannerUrl)" alt="">
        <div class="pack-heading-text"><p>{{ [gameName(pack.gameCode),pack.code].filter(Boolean).join(' · ') }}</p><h1>{{ packTitle(pack) }}</h1>
          <template v-if="pack.officialProduct">
            <p v-if="locale==='ko'" lang="en">{{ pack.officialProduct.englishName }}</p>
            <dl class="pack-dates">
              <div><dt>{{ pt('북미 일반 발매') }}</dt><dd>{{ pack.officialProduct.launchDate }}</dd></div>
              <div><dt>{{ pt('북미 공인점 선행 발매') }}</dt><dd>{{ pack.officialProduct.otsDate }}</dd></div>
              <div><dt>{{ pt('공식 상품 구성') }}</dt><dd>{{ countLabel(pack.officialProduct.setSize) }}</dd></div>
            </dl>
            <a v-if="sourceLink(pack.officialProduct.sourceUrl)" :href="sourceLink(pack.officialProduct.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ pt('공식 상품 안내') }}</a>
          </template>
          <dl v-else-if="pack.metadata?.jp || pack.metadata?.kr" class="pack-dates">
            <div v-if="pack.metadata.jp"><dt>{{ pt('일본 발매') }}</dt><dd>{{ pack.metadata.jp }}</dd></div>
            <div v-if="pack.metadata.kr"><dt>{{ pt('한국 발매') }}</dt><dd>{{ pack.metadata.kr }}</dd></div>
          </dl>
          <p v-else-if="pack.releaseLabel || pack.releaseDate">{{ pack.releaseLabel || pack.releaseDate }}</p>
          <p v-if="pack.metadata?.note">{{ pack.metadata.note }}</p>
        </div>
      </header>
      <details v-if="productReference" :key="pack.id" class="pack-reference">
        <summary>{{ pt('상품 출처') }}</summary>
        <p>{{ regionName(productReference.region) }} · <time :datetime="productReference.releaseDate">{{ productReference.releaseDate }}</time></p>
        <ul>
          <li><a :href="sourceLink(productReference.verificationUrl)" target="_blank" rel="noopener noreferrer">{{ pt('공식 상품 안내') }}</a></li>
          <li><a :href="sourceLink(productReference.documentUrl)" :title="productReference.title+' · '+productReference.section" target="_blank" rel="noopener noreferrer">{{ pt('나무위키 참고 문서') }}</a></li>
          <li><a :href="sourceLink(productReference.snapshotUrl)" target="_blank" rel="noopener noreferrer">{{ pt('스냅샷') }} {{ productReference.snapshotDate }}</a></li>
        </ul>
      </details>
      <section v-if="otherEvents.length||releaseError" class="pack-releases">
        <h2>{{ pt('지역별 발매 일정') }}</h2>
        <ul><li v-for="e in otherEvents" :key="e.id"><span>{{ regionName(e.region) }}</span><time :datetime="e.releaseDate">{{ e.releaseDate }}</time>
          <a v-if="sourceLink(e.sourceUrl)" :href="sourceLink(e.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ pt('발매 정보 출처') }} ↗</a></li></ul>
        <p v-if="releaseError" role="status">{{ pt('지역별 일정을 불러오지 못했습니다.') }} <button class="text-button" @click="releaseRetry++">{{ pt('다시 시도') }}</button></p>
        <button v-else-if="(releasePage+1)*24<releaseTotal" class="text-button" :disabled="releaseBusy" @click="releasePage++">{{ pt('더 보기') }}</button>
      </section>
      <div v-if="pack.total && showInclusions" class="pack-counts" role="group" :aria-label="pt('수록 구분')">
        <button type="button" :aria-pressed="!inclusion" @click="inclusion=''"><span>{{ pt('전체') }}</span><strong>{{ pack.total.toLocaleString(locale) }}</strong></button>
        <button v-for="(label,key) in inclusions" :key="key" type="button" :aria-pressed="inclusion===key" @click="inclusion=inclusion===key?'':key"><span>{{ pt(label) }}</span><strong>{{ pack[countFields[key]].toLocaleString(locale) }}</strong></button>
      </div>
      <details class="pack-breakdown" @toggle="e=>{if(e.target.open && hasMore)loadMore(true)}">
        <summary>{{ pt('수록 구성') }} · {{ pt('공개 카드') }} {{ pack.total ?? 0 }}</summary>
        <p>{{ pt('상품 전체 수록 수') }} · {{ announced??pt('수록 수 미확인') }}</p>
        <p v-if="moreBusy">{{ cards.length }} / {{ pack.total }}</p>
        <div v-else-if="!hasMore"><div v-for="(group,i) in [pack.rarityCounts?pack.rarityCounts.map(r=>[r.rarity,r.count]):breakdown[0],breakdown[1]]" :key="i"><strong>{{ pt(i?'카드 종류':'레어도') }}</strong>
          <span v-for="[label,n] in group" :key="label">{{ facetLabel(i?'type':'rarity',label,pack.gameCode) }} {{ n }}</span><span v-if="!i && pack.unknownRarityCount">{{ pt('레어도 미기재') }} {{ pack.unknownRarityCount }}</span><small v-if="!group.length">{{ pt('미분류') }}</small></div></div>
      </details>
      <div class="pack-toolbar">
        <h2 ref="listTop" tabindex="-1">{{ pt('수록 카드') }} <small v-if="pack.total&&!showInclusions">{{ pack.total.toLocaleString(locale) }}</small></h2>
        <div v-if="pack.total" class="pack-controls"><input type="search" v-model="q" :aria-label="pt('팩에서 검색')" :placeholder="pt('카드명·번호·효과')">
          <select v-model="sort" :aria-label="pt('수록 카드 정렬')" @change="page=0">
            <option v-for="(label,key) in {source:'수록 순',number:'번호 순',rarity:'레어도 순',name:'이름 순'}" :key="key" :value="key">{{ pt(label) }}</option>
          </select>
          <PackGallery :key="pack.id" :pack="pack" :cards="cards" :loading="moreBusy" :has-more="hasMore" :error="moreError" @load="loadMore(true)" @pick="pickCard"/>
        </div>
      </div>
      <p v-if="q || inclusion" class="pack-result" role="status">{{ countLabel(filtered.length) }} <button class="text-button" type="button" @click="q='';inclusion=''">{{ pt('필터 지우기') }}</button></p>
      <p v-if="moreBusy" class="muted" role="status">{{ pt('카드 불러오는 중…') }} {{ cards.length }} / {{ pack.total }}</p>
      <p v-if="moreError" class="inline-error" role="alert">{{ moreError }} <button type="button" class="text-button" @click="loadMore(true)">{{ pt('다시 시도') }}</button></p>
      <p v-if="!shown.length && !moreBusy" class="state">{{ pt(pack.total?'검색 결과가 없습니다.':'수록 카드가 아직 없습니다.') }}</p>
      <div v-else class="pack-list">
        <template v-for="(card,i) in shown" :key="card.id">
          <h3 v-if="special && card.product && (i===0 || shown[i-1].product!==card.product)" class="pack-product">{{ card.product }} <small v-if="card.productDate">{{ card.productDate }}</small></h3>
          <details :id="'pack-card-'+card.id" class="pack-row" :open="expanded===card.id" @toggle="toggle(card.id,$event)">
            <summary><span class="pack-number">{{ card.number }}</span><span class="pack-name"><strong :lang="locale">{{ card.language===locale && card.name ? card.name : pt('이 언어의 카드명 미등록') }}</strong><CardTextCredit v-if="card.language===locale" :card="card"/><small v-if="card.inclusion || card.type"><span v-if="card.inclusion">{{ facetLabel('inclusion',card.inclusion) }}</span><span v-if="card.type">{{ card.inclusion?' · ':'' }}{{ facetLabel('type',card.type,pack.gameCode) }}</span></small><RiftEffectSummary v-if="pack.gameCode==='RIFTBOUND'" :card="card"/></span><span v-if="card.rarity" class="pack-rarity">{{ shortRarity(card) }}</span><span class="chevron" aria-hidden="true"></span></summary>
            <CardDetails v-if="visited.has(card.id)" :card-id="card.id" lazy/>
          </details>
        </template>
      </div>
      <nav v-if="pages>1 || hasMore" class="pagination" :aria-label="pt('결과 페이지')">
        <button type="button" class="secondary" :disabled="!page" @click="goPage(page-1)">{{ pt('이전') }}</button>
        <span>{{ page+1 }} / {{ hasMore && !q && !inclusion ? Math.ceil(pack.total/pageSize) : pages }}</span>
        <button type="button" class="secondary" :disabled="moreBusy || (page+1>=pages && !hasMore)" @click="goPage(page+1)">{{ pt('다음') }}</button>
      </nav>
      <LegacyPackNavigation v-if="pack.metadata?.id || pack.officialProduct" :key="pack.id" :pack="pack"/>
    </template>
  </div>
</template>
<style scoped>
.pack-breakdown{border-bottom:1px solid var(--bd);padding-block:5px;font-size:.85rem}.pack-breakdown summary{cursor:pointer;min-height:38px;padding:6px 0}.pack-breakdown>div>div{display:flex;flex-wrap:wrap;gap:.3rem .8rem;margin:.4rem 0}
.pack-page{max-width:900px;margin:0 auto;padding:12px 0 24px}.pack-back{display:inline-flex;align-items:center;gap:7px;min-height:44px;text-decoration:none;font-size:.9rem;font-weight:650}.pack-back:hover{text-decoration:underline}
.pack-heading{display:flex;align-items:center;gap:22px;padding:16px 0 20px}.pack-cover{width:clamp(100px,19%,160px);height:102px;object-fit:cover;border-radius:8px;background:var(--bd)}.pack-heading-text{min-width:0}.pack-heading h1{margin:4px 0 8px;font-size:clamp(1.65rem,3.6vw,2.35rem);line-height:1.17;overflow-wrap:anywhere;letter-spacing:-.035em}.pack-heading p{color:var(--mu);margin:0;font-size:.84rem}
.pack-dates{display:flex;flex-wrap:wrap;gap:3px 18px;margin:0;font-size:.85rem}.pack-dates div{display:flex;gap:6px}.pack-dates dt{color:var(--mu)}.pack-dates dd{margin:0;font-variant-numeric:tabular-nums}
.pack-counts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:4px;border:1px solid var(--bd);border-radius:10px;background:var(--sf);gap:4px}.pack-counts button{display:flex;align-items:baseline;justify-content:space-between;gap:4px;min-height:46px;padding:8px 13px;border:0;border-radius:6px;color:var(--tx);background:transparent}.pack-counts button[aria-pressed=true]{background:var(--ac);color:var(--sf)}.pack-counts span{font-size:.86rem}.pack-counts strong{font-size:1.25rem;line-height:1.2;font-variant-numeric:tabular-nums}
.pack-toolbar,.pack-controls,.pack-result{display:flex;align-items:center;gap:10px}.pack-toolbar{justify-content:space-between;margin:23px 0 12px}.pack-toolbar h2{margin:0;font-size:1.1rem;scroll-margin-top:90px}.pack-controls input{width:clamp(150px,27vw,290px);min-height:44px;margin:0}.pack-result{font-size:.88rem;color:var(--mu)}
.pack-list{border:1px solid var(--bd);background:var(--sf);border-radius:12px;overflow:clip}.pack-row{scroll-margin-top:76px}.pack-row+.pack-row,.pack-product{border-top:1px solid var(--bd)}.pack-row summary{display:grid;grid-template-columns:minmax(110px,.34fr) minmax(0,1fr) auto 10px;gap:14px;align-items:center;min-height:65px;padding:10px 17px;list-style:none}.pack-row summary::-webkit-details-marker{display:none}.pack-row summary:hover{background:var(--bg)}.pack-row[open] summary{background:var(--bg);box-shadow:inset 3px 0 var(--ac)}.pack-row[open] .chevron{transform:rotate(225deg)}.pack-name strong,.pack-name small{display:block;overflow-wrap:anywhere}.pack-name small,.pack-rarity,.pack-number,.pack-product small{color:var(--mu);font-size:.78rem}.pack-number{overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.pack-rarity{max-width:17ch;overflow-wrap:anywhere}.pack-row :deep(.details-body){padding:16px}.pack-row-actions{display:flex;justify-content:flex-end;margin-top:16px;border-top:1px solid var(--bd);padding-top:12px}.pack-product{font-size:.95rem;padding:10px 16px;margin:0;background:var(--bg);color:var(--tx)}.pack-product small{font-weight:400;margin-left:4px}
@media(max-width:600px){.pack-page{padding-top:5px}.pack-heading{gap:13px;padding:8px 0 17px}.pack-cover{width:76px;height:85px}.pack-heading h1{font-size:1.45rem}.pack-counts button{display:grid;justify-items:start;align-items:center;align-content:center;padding:6px 7px;line-height:1.22}.pack-counts span{font-size:.72rem}.pack-counts strong{font-size:1.05rem}.pack-toolbar{margin-top:18px;flex-wrap:wrap}.pack-controls{flex:1 1 250px}.pack-controls input{width:100%;min-width:0}.pack-row summary{grid-template-columns:minmax(0,1fr) 10px;gap:2px 10px;padding:9px 12px}.pack-row .chevron{grid-area:1/2/3/3}.pack-rarity{display:none}.pack-number{grid-area:1/1}.pack-name{grid-area:2/1}.pack-row :deep(.details-body){padding:13px}.pack-row :deep(.lib-actions){display:grid;justify-items:start;gap:5px}}
</style>
<style scoped>
.pack-heading h1,.pack-counts span{word-break:keep-all;overflow-wrap:anywhere}
.pack-reference{margin-block:0 .75rem;border-block-end:1px solid var(--bd);font-size:.9rem}
.pack-reference summary{padding:.8rem 0;width:fit-content;min-height:44px;cursor:pointer}
.pack-reference p{margin:0;color:var(--tx);overflow-wrap:anywhere}
.pack-reference time{white-space:nowrap;font-variant-numeric:tabular-nums}
.pack-reference ul{display:flex;flex-wrap:wrap;gap:0 1rem;list-style:none;margin:0;padding:0}
.pack-reference a{display:inline-flex;align-items:center;min-height:44px;text-underline-offset:.18em}
.pack-row[open] .pack-raw-type{display:none}
.pack-releases{margin:0 0 1rem;border-top:1px solid var(--bd);border-bottom:1px solid var(--bd);padding:.65rem 0}.pack-releases h2{font-size:1rem;margin:.1rem 0}.pack-releases ul{list-style:none;margin:0;padding:0}.pack-releases li{display:flex;align-items:baseline;flex-wrap:wrap;gap:.3rem .75rem;min-height:34px;padding:.3rem 0}.pack-releases time{font-variant-numeric:tabular-nums}.pack-releases a,.pack-releases p{font-size:.85rem}
@media(max-width:480px){
  .pack-toolbar h2{flex-basis:100%}.pack-controls{flex-basis:100%}
  .pack-counts button{grid-template-rows:1fr auto;align-items:start;align-self:stretch;text-align:start}
  .pack-counts span{line-height:1.2}.pack-counts strong{align-self:end}
}
</style>
