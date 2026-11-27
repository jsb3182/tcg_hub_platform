<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { request,mediaPath } from '../api'
import { gameName,t } from '../i18n'
import { packTitle,pt } from '../pack'
const route=useRoute(), router=useRouter()
const sections=[['SCHEDULE','팩 발매 일정'],['DISTRIBUTION','동봉 · 배포 카드'],['PREMIERE','TCG 월드 프리미어 카드'],['ARCHIVE','장기 미수록 카드']]
const packs=ref([]), loading=ref(true), error=ref(''), retry=ref(0), limits=ref({})
const game=computed(()=>typeof route.query.game==='string'?route.query.game:'YUGIOH')
const query=computed(()=>typeof route.query.q==='string'?route.query.q:'')
const games=computed(()=>[...new Set(packs.value.map(p=>p.gameCode))].sort())
const matching=computed(()=>packs.value.filter(p=>(!game.value||p.gameCode===game.value) &&
  [p.name,p.officialProduct?.englishName,p.code,p.latestProduct,p.metadata?.kind].some(v=>String(v??'').toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()))))
const rows=computed(()=>sections.map(([key,title])=>{
  const items=matching.value.filter(p=>p.group===key)
  if(key==='PREMIERE')items.sort((a,b)=>(a.officialProduct?.launchDate||a.releaseDate||'9999').localeCompare(b.officialProduct?.launchDate||b.releaseDate||'9999'))
  return {key,title,items:items.slice(0,limits.value[key]||16),total:items.length}
}).filter(s=>s.total))
function change(key,value){router.replace({name:'releases',query:{...route.query,[key]:value}})}
watch([game,query],()=>{limits.value={}})
watch(retry,async(_,__,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort());loading.value=true;error.value=''
  try{const data=await request('/releases',{signal:abort.signal});if(!abort.signal.aborted)packs.value=data}
  catch(e){if(!abort.signal.aborted)error.value=e.message}
  finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})
function range(p){return [...new Set([p.firstProductDate,p.lastProductDate].filter(Boolean))].join(' – ')}
</script>
<template>
  <header class="release-head"><h1>{{ t('발매 일정') }}</h1>
    <div class="release-filters"><label>{{ t('게임') }}<select :value="game" @change="change('game',$event.target.value)"><option value="">{{ t('전체') }}</option><option v-for="g in games" :key="g" :value="g">{{ gameName(g) }}</option></select></label>
      <label>{{ t('팩 검색') }}<input type="search" maxlength="120" :value="query" :placeholder="t('팩 이름 또는 코드')" @input="change('q',$event.target.value)"></label></div>
  </header>
  <p v-if="loading" role="status">{{ t('불러오는 중…') }}</p>
  <p v-else-if="error" role="alert">{{ error }} <button class="secondary" @click="retry++">{{ t('다시 시도') }}</button></p>
  <p v-else-if="!rows.length" class="state">{{ t('조건에 맞는 팩이 없습니다.') }}</p>
  <template v-else><nav class="release-sections" :aria-label="t('팩 분류')"><a v-for="s in rows" :key="s.key" :href="'#release-'+s.key">{{ t(s.title) }}</a></nav>
  <section v-for="s in rows" :id="'release-'+s.key" :key="s.key" class="release-section">
    <h2>{{ t(s.title) }} <small>{{ s.total }}</small></h2>
    <ul><li v-for="p in s.items" :key="p.id"><RouterLink :to="{name:'pack',params:{id:p.id},query:route.query}">
      <div class="release-row-title"><small>{{ [p.code,p.metadata?.kind||gameName(p.gameCode)].filter(Boolean).join(' · ') }}</small><strong>{{ packTitle(p) }}</strong>
        <span v-if="p.group==='DISTRIBUTION'||p.group==='ARCHIVE'">{{ t('상품 수') }} {{ p.productCount }} <template v-if="range(p)">· {{ range(p) }}</template></span>
        <span v-else-if="p.officialProduct">{{ pt('북미 일반 발매') }} · {{ p.officialProduct.launchDate }}</span>
        <span v-else>{{ [p.metadata?.jp||p.releaseDate,p.metadata?.kr ? t('한국 발매 예상')+' '+p.metadata.kr : !p.releaseDate ? p.releaseLabel : ''].filter(Boolean).join(' · ') || t('일정 미정') }}</span>
        <span v-if="p.latestProduct && (p.group==='DISTRIBUTION'||p.group==='ARCHIVE')">{{ t('최근 상품') }} · {{ p.latestProduct }}</span>
      </div>
      <div class="release-count"><template v-if="p.total || !p.officialProduct"><b>{{ p.total }}</b> {{ t('수록 카드') }}</template><template v-else>{{ pt('도감 등록 전') }}</template><small v-if="p.newCount">{{ t('신규') }} {{ p.newCount }}</small></div>
      <img v-if="mediaPath(p.bannerUrl)" :src="mediaPath(p.bannerUrl)" alt="" loading="lazy">
    </RouterLink></li></ul>
    <button v-if="s.total>s.items.length" class="secondary" @click="limits={...limits,[s.key]:s.items.length+24}">{{ t('더 보기') }} ({{ s.items.length }}/{{ s.total }})</button>
  </section></template>
</template>
<style scoped>
.release-head,.release-section,.release-sections{max-width:62rem;margin-inline:auto}.release-head{display:flex;align-items:end;justify-content:space-between;gap:1.5rem;margin-block:2.4rem 1.2rem}.release-head h1{margin:0}.release-filters,.release-sections{display:flex;flex-wrap:wrap;gap:.8rem}.release-filters label{display:grid;gap:.2rem;color:var(--mu);font-size:.84rem}.release-filters :is(select,input){min-height:44px;border:1px solid var(--bd);background:var(--sf);color:var(--tx);border-radius:6px;padding:.4rem .65rem;max-width:100%}.release-sections{border-block:1px solid var(--bd);gap:.35rem 1.25rem}.release-sections a{padding:.65rem 0;font-weight:600;text-underline-offset:.22em}.release-section{margin-block:2.4rem;scroll-margin-top:6rem}.release-section h2{font-size:1.35rem;margin-bottom:.4rem}.release-section h2 small,.release-row-title small,.release-count small,.release-row-title span{color:var(--mu);font-size:.84rem;font-weight:450}.release-section ul{list-style:none;padding:0;margin:0}.release-section li{border-bottom:1px solid var(--bd)}.release-section li>a{display:flex;align-items:center;gap:1rem;min-height:78px;padding:.8rem .35rem;text-decoration:none;color:var(--tx)}.release-section li>a:hover strong{text-decoration:underline;text-underline-offset:.2em;color:var(--ac)}.release-row-title{display:grid;min-width:0;flex:1;overflow-wrap:anywhere}.release-row-title strong{font-size:1.08rem}.release-count{text-align:end;font-size:.78rem}.release-count b{color:var(--ac);font-size:1rem}.release-count small{display:block}.release-section img{width:5.75rem;height:3.25rem;object-fit:cover;border-radius:4px}.release-section>button{margin-top:.8rem}@media(max-width:650px){.release-head{display:block;margin-block:1.35rem}.release-filters{margin-top:.7rem;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr)}.release-section img{width:3.25rem;height:2.9rem}.release-count{max-width:4.4rem}.release-section li>a{gap:.55rem}.release-sections{column-gap:.9rem}}
</style>
