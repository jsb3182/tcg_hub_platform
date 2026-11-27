<script setup>
import {computed,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {gameCodes,gameName} from '../i18n'
import {pt} from '../pack'
import {request} from '../api'
const props=defineProps({game:String}),route=useRoute(),router=useRouter(),open=computed(()=>route.query.browse==='1')
const game=computed(()=>gameCodes.includes(route.query.packGame)?route.query.packGame:'')
const q=computed(()=>typeof route.query.packQuery==='string'?route.query.packQuery:'')
const draft=ref(q.value),items=ref([]),total=ref(0),loading=ref(false),error=ref(''),retry=ref(0)
const page=computed(()=>/^\d{1,5}$/.test(route.query.packPage||'')?Number(route.query.packPage):0)
function set(params){const query={...route.query,...params};for(const k of Object.keys(query))if(!query[k])delete query[k];router.replace({query,hash:open.value?'#catalog-packs':''})}
watch(q,v=>{draft.value=v})
watch([open,game,q,page,retry],async([show,g,query,n],_,clean)=>{
  const abort=new AbortController();clean(()=>abort.abort());items.value=[];error.value='';if(!show)return
  loading.value=true
  try{const res=await request('/catalog-packs?'+new URLSearchParams({game:g,q:query,page:n,size:24}),{signal:abort.signal});if(!abort.signal.aborted){items.value=res.items;total.value=res.total}}
  catch(e){if(!abort.signal.aborted)error.value=e.message}
  finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})
</script>
<template><section id="catalog-packs" class="pack-finder">
  <button type="button" class="text-button" :aria-expanded="open" @click="set({browse:open?null:'1',packGame:route.query.packGame||(gameCodes.includes(props.game)?props.game:null)})">{{ pt('수록 팩 찾기') }} <span aria-hidden="true">{{ open?'−':'+' }}</span></button>
  <div v-if="open"><form @submit.prevent="set({packQuery:draft.trim(),packPage:null})">
    <label>{{ pt('게임') }}<select :value="game" @change="set({packGame:$event.target.value,packPage:null})"><option value="">{{ pt('모든 종목') }}</option><option v-for="g in gameCodes" :value="g" :key="g">{{ gameName(g) }}</option></select></label>
    <label>{{ pt('팩 검색') }}<input v-model="draft" type="search" maxlength="100"></label><button class="secondary">{{ pt('검색') }}</button>
  </form>
  <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ pt('다시 시도') }}</button></p>
  <p v-else-if="loading" role="status">{{ pt('불러오는 중…') }}</p>
  <template v-else><small role="status">{{ pt('상품 수') }} {{ total }}</small>
    <ul><li v-for="p in items" :key="p.id"><RouterLink :to="{name:'pack',params:{id:p.id},query:{...route.query,browse:'1',section:'catalog-packs'}}">
      <span>{{ p.name }}<small>{{ [gameName(p.gameCode),p.code].filter(Boolean).join(' · ') }}</small></span>
      <small>{{ p.catalogCount==null?pt('수록 수 미확인'):pt('공개 카드')+' '+p.catalogCount }}</small></RouterLink></li></ul>
    <nav v-if="total>24" class="pagination"><button class="secondary" :disabled="!page" @click="set({packPage:page-1})">{{ pt('이전') }}</button>
      <span>{{ page+1 }} / {{ Math.ceil(total/24) }}</span><button class="secondary" :disabled="(page+1)*24>=total" @click="set({packPage:page+1})">{{ pt('다음') }}</button></nav>
  </template></div></section></template>
<style scoped>
.pack-finder{scroll-margin-top:5rem}.pack-finder>button{font-weight:650;min-height:40px}.pack-finder form{display:flex;align-items:end;flex-wrap:wrap;gap:.55rem;margin:.4rem 0}.pack-finder label{flex:1 1 7rem;min-width:0;display:grid;font-size:.84rem}.pack-finder :is(input,select){width:100%;min-width:0;min-height:40px;border:1px solid var(--bd);border-radius:5px;padding:.4rem;background:var(--sf);color:var(--tx)}.pack-finder ul{list-style:none;padding:0}.pack-finder li a{display:flex;justify-content:space-between;align-items:center;gap:6px;min-height:48px;border-bottom:1px solid var(--bd);text-decoration:none;color:var(--tx)}.pack-finder li a:hover{text-decoration:underline}.pack-finder small{display:block;color:var(--mu)}
</style>
