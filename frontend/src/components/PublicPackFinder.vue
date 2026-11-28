<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {gameName,locale} from '../i18n'
import {pt} from '../pack'
import {request} from '../api'

const props=defineProps({games:{type:Array,required:true},term:{type:String,required:true}})
const route=useRoute(),router=useRouter()
const expanded=computed(()=>route.query.browse==='1')
const visible=computed(()=>expanded.value || Boolean(props.term))
const game=computed(()=>props.games.includes(route.query.catalogGame)?route.query.catalogGame:props.games[0]||'')
const page=computed(()=>expanded.value && /^\d{1,5}$/.test(route.query.packPage||'')?Number(route.query.packPage):0)
const size=computed(()=>expanded.value?24:4)
const items=ref([]),total=ref(0),loading=ref(false),error=ref(''),retry=ref(0)
const finderHeading=ref(),browseButton=ref()

function set(edits){
  const query={...route.query,game:props.games.join(','),q:props.term,...edits}
  delete query.packGame
  delete query.packQuery
  for(const key of Object.keys(query))if(!query[key])delete query[key]
  return router.replace({name:'releases',query,hash:'#catalog-packs'})
}
async function browse(edits){
  await set(edits)
  await nextTick()
  const target=finderHeading.value||browseButton.value
  target?.focus({preventScroll:true})
  target?.scrollIntoView({block:'nearest'})
}
watch([visible,game,()=>props.term,page,size,retry],async([show,scope,q,n,limit],_,cleanup)=>{
  const controller=new AbortController(),signal=controller.signal
  cleanup(()=>controller.abort())
  items.value=[];total.value=0;error.value='';loading.value=show
  if(!show)return
  try{
    const params=new URLSearchParams({game:scope,q,page:n,size:limit})
    const result=await request('/catalog-packs?'+params,{signal})
    if(signal.aborted)return
    const last=Math.max(0,Math.ceil(result.total/limit)-1)
    if(n>last){await set({packPage:last});return}
    items.value=result.items;total.value=result.total
  }catch(cause){if(!signal.aborted)error.value=cause.message}
  finally{if(!signal.aborted)loading.value=false}
},{immediate:true})
</script>
<template>
  <section id="catalog-packs" class="pack-finder" :aria-label="pt('팩 도감')">
    <button v-if="!visible" ref="browseButton" class="text-button browse" type="button" aria-expanded="false"
      @click="browse({browse:'1',packPage:null})">{{ pt('수록 팩 찾기') }} <span aria-hidden="true">＋</span></button>
    <template v-else>
      <header class="finder-heading">
        <h2 ref="finderHeading" tabindex="-1">{{ pt('팩 도감') }}</h2>
        <small v-if="!loading && !error" role="status">{{ pt('상품 수') }} {{ total.toLocaleString(locale) }}</small>
        <button v-if="expanded" class="text-button" type="button" :aria-label="pt('팩 도감')+' · '+pt('닫기')"
          @click="browse({browse:null,packPage:null})">{{ pt('닫기') }}</button>
      </header>
      <label v-if="games.length>1" class="finder-scope">{{ pt('게임') }}
        <select :value="game" @change="set({catalogGame:$event.target.value,packPage:null})">
          <option v-for="code in games" :key="code" :value="code">{{ gameName(code) }}</option>
        </select>
      </label>
      <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ pt('다시 시도') }}</button></p>
      <p v-else-if="loading" role="status">{{ pt('불러오는 중…') }}</p>
      <p v-else-if="!items.length" class="finder-empty">{{ pt('조건에 맞는 팩이 없습니다.') }}</p>
      <template v-else>
        <ul><li v-for="p in items" :key="p.id">
          <RouterLink :to="{name:'pack',params:{id:p.id},query:{...route.query,section:'catalog-packs'}}">
            <span class="finder-product"><strong>{{ p.name }}</strong><small>{{ [gameName(p.gameCode),p.code].filter(Boolean).join(' · ') }}</small></span>
            <small class="finder-count">{{ p.catalogCount==null?pt('수록 수 미확인'):pt('공개 카드')+' '+p.catalogCount.toLocaleString(locale) }}</small>
            <span class="finder-arrow" aria-hidden="true">→</span>
          </RouterLink>
        </li></ul>
        <button v-if="!expanded && total>size" class="text-button browse" type="button" @click="browse({browse:'1',packPage:null})">
          {{ pt('수록 팩 찾기') }} ({{ size }} / {{ total.toLocaleString(locale) }})
        </button>
        <nav v-if="expanded && total>size" class="pagination" :aria-label="pt('결과 페이지')">
          <button class="secondary" :disabled="!page" @click="browse({packPage:page-1})">{{ pt('이전') }}</button>
          <span>{{ page+1 }} / {{ Math.ceil(total/size) }}</span>
          <button class="secondary" :disabled="(page+1)*size>=total" @click="browse({packPage:page+1})">{{ pt('다음') }}</button>
        </nav>
      </template>
    </template>
  </section>
</template>
<style scoped>
.pack-finder{margin:.6rem 0 1rem;scroll-margin-top:5rem}
.pack-finder .browse,.finder-heading button{min-height:44px}
.finder-heading{display:flex;align-items:center;flex-wrap:wrap;gap:.2rem .65rem;min-height:48px;border-bottom:1px solid var(--bd)}
.finder-heading h2{font-size:1.16rem;margin:0;scroll-margin-top:5rem}.finder-heading button{margin-inline-start:auto}
.pack-finder small,.finder-empty,.finder-scope{color:var(--mu);font-size:.86rem}
.pack-finder ul{list-style:none;margin:0;padding:0}
.pack-finder li a{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:.6rem;min-height:58px;padding:.5rem .18rem;border-bottom:1px solid var(--bd);text-decoration:none;color:var(--tx)}
.finder-product{display:grid;gap:.12rem;overflow-wrap:anywhere}.finder-product strong{font-weight:650}
.pack-finder li a:hover strong,.pack-finder li a:focus-visible strong{text-decoration:underline;text-underline-offset:.18em}
.finder-count{font-variant-numeric:tabular-nums;max-width:8rem;text-align:end}.finder-arrow{color:var(--ac)}
.finder-scope{display:flex;align-items:center;gap:.5rem;margin-top:.6rem}.finder-scope select{background:var(--sf);color:var(--tx);border:1px solid var(--bd);min-height:44px;border-radius:6px;padding:.4rem}
@media(max-width:550px){.finder-count{font-size:.78rem;max-width:5.8rem}}
</style>
