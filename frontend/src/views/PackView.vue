<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { mediaPath, request } from '../api'
import { gameName, locale } from '../i18n'
import { countLabel, facetLabel, inclusions, pt } from '../pack'
import { pngSnapshot } from '../pngSnapshot'
import CardDetails from '../components/CardDetails.vue'
import PackGallery from '../components/PackGallery.vue'
import PngExport from '../components/PngExport.vue'

const route=useRoute()
const pack=ref(null), cards=ref([]), expanded=ref(null), page=ref(0), packPage=ref(0)
const loading=ref(true), moreBusy=ref(false), hasMore=ref(false), error=ref(''), moreError=ref(''), retry=ref(0)
const q=ref(''), inclusion=ref(''), listTop=ref()
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
const backTo=computed(()=>({name:'releases',query:{...route.query}}))
let controller, loadToEnd=false
function apiPage(n,signal){
  return request('/packs/'+encodeURIComponent(route.params.id)+'?'+new URLSearchParams({lang:locale.value,page:n,size:200}),{signal})
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
watch([()=>route.params.id,locale,retry],async([id],previous,onCleanup)=>{
  const different=previous?.[0]!==id
  const controllerForRequest=new AbortController()
  controller=controllerForRequest
  const signal=controllerForRequest.signal
  onCleanup(()=>controllerForRequest.abort())
  if(different){q.value='';inclusion.value='';expanded.value=null;page.value=0}
  loading.value=true;error.value='';moreError.value='';moreBusy.value=false;hasMore.value=false;loadToEnd=false
  try{
    const data=await apiPage(0,signal)
    if(signal.aborted)return
    const {cards:rows,...header}=data
    pack.value=header;cards.value=rows;packPage.value=0;hasMore.value=data.hasMore
    if(different || expanded.value===null)expanded.value=rows[0]?.id ?? null
    if(hasMore.value && (q.value || inclusion.value || page.value>0))await loadMore(true)
  }catch(e){if(!signal.aborted)error.value=e.message}
  finally{if(!signal.aborted)loading.value=false}
},{immediate:true})
watch([q,inclusion],()=>{
  page.value=0;expanded.value=filtered.value[0]?.id ?? null
  if(hasMore.value)loadMore(true)
})
function toggle(id,event){
  if(event.currentTarget.open)expanded.value=id
  else if(expanded.value===id)expanded.value=null
}
async function goPage(n){
  if(n>=pages.value && hasMore.value) await loadMore()
  if(n<0 || n>=pages.value)return
  page.value=n;expanded.value=shown.value[0]?.id ?? null
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
function snapshot(card,article,width){
  return pngSnapshot(article,card.name,[pack.value.name,card.number].filter(Boolean).join(' · '),width)
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
        <div class="pack-heading-text"><p>{{ [gameName(pack.gameCode),pack.code].filter(Boolean).join(' · ') }}</p><h1>{{ pack.name }}</h1>
          <dl v-if="pack.metadata?.jp || pack.metadata?.kr" class="pack-dates">
            <div v-if="pack.metadata.jp"><dt>{{ pt('일본 발매') }}</dt><dd>{{ pack.metadata.jp }}</dd></div>
            <div v-if="pack.metadata.kr"><dt>{{ pt('한국 발매') }}</dt><dd>{{ pack.metadata.kr }}</dd></div>
          </dl>
          <p v-else-if="pack.releaseLabel || pack.releaseDate">{{ pack.releaseLabel || pack.releaseDate }}</p>
          <p v-if="pack.metadata?.note">{{ pack.metadata.note }}</p>
        </div>
      </header>
      <div class="pack-counts" role="group" :aria-label="pt('수록 구분')">
        <button type="button" :aria-pressed="!inclusion" @click="inclusion=''"><span>{{ pt('전체') }}</span><strong>{{ pack.total.toLocaleString(locale) }}</strong></button>
        <button v-for="(label,key) in inclusions" :key="key" type="button" :aria-pressed="inclusion===key" @click="inclusion=inclusion===key?'':key"><span>{{ pt(label) }}</span><strong>{{ pack[countFields[key]].toLocaleString(locale) }}</strong></button>
      </div>
      <div class="pack-toolbar">
        <h2 ref="listTop" tabindex="-1">{{ pt('수록 카드') }}</h2>
        <div class="pack-controls"><input type="search" v-model="q" :aria-label="pt('팩에서 검색')" :placeholder="pt('카드명·번호·효과')">
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
            <summary><span class="pack-number">{{ card.number }}</span><span class="pack-name"><strong :lang="card.language || ''">{{ card.name }}</strong><small v-if="card.inclusion || card.type">{{ [card.inclusion && facetLabel('inclusion',card.inclusion),card.type && facetLabel('type',card.type)].filter(Boolean).join(' · ') }}</small></span><span v-if="card.rarity" class="pack-rarity">{{ card.rarity }}</span><span class="chevron" aria-hidden="true"></span></summary>
            <CardDetails :card-id="card.id" lazy>
              <template #after-card="{card:details,article}"><div class="pack-row-actions">
                <PngExport choose-width :name="[card.number,details.name].filter(Boolean).join(' ')" :label="pt('카드 정보 PNG')" :render="width=>snapshot(details,article,width)"/>
              </div></template>
            </CardDetails>
          </details>
        </template>
      </div>
      <nav v-if="pages>1 || hasMore" class="pagination" :aria-label="pt('결과 페이지')">
        <button type="button" class="secondary" :disabled="!page" @click="goPage(page-1)">{{ pt('이전') }}</button>
        <span>{{ page+1 }} / {{ hasMore && !q && !inclusion ? Math.ceil(pack.total/pageSize) : pages }}</span>
        <button type="button" class="secondary" :disabled="moreBusy || (page+1>=pages && !hasMore)" @click="goPage(page+1)">{{ pt('다음') }}</button>
      </nav>
    </template>
  </div>
</template>
<style scoped>
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
@media(max-width:480px){
  .pack-toolbar h2{flex-basis:100%}.pack-controls{flex-basis:100%}
  .pack-counts button{grid-template-rows:1fr auto;align-items:start;align-self:stretch;text-align:start}
  .pack-counts span{line-height:1.2}.pack-counts strong{align-self:end}
}
</style>
