<script setup>
import { t as uiText } from '../i18n'

import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import { gameName, languages, locale } from '../i18n'
import CardTextCredit from '../components/CardTextCredit.vue'
import LibraryAccess from '../components/LibraryAccess.vue'
import CatalogPicker from '../components/CatalogPicker.vue'
import LibraryThumbnail from '../components/LibraryThumbnail.vue'
import ArtworkCredit from '../components/ArtworkCredit.vue'
const session = useSession(), route = useRoute()
const games = ref([]), game = ref(''), page = ref(0), result = ref(null), error = ref(''), notice = ref('')
const selected = ref(null), quantity = ref(1), busy = ref(false), retry = ref(0)
const quantityDialog = ref(null), quantityInput = ref(null), formError = ref('')
const filters=reactive({q:'',rarity:'',minQuantity:'',maxQuantity:'',edition:'',condition:'',tradable:''})
const editions=['und','ko','en','ja'], conditions=['UNSPECIFIED','NM','LP','MP','HP','DMG']
const edition=ref('und'), condition=ref('UNSPECIFIED'), tradable=ref(false), stats=ref([])
const view=ref('grid'), pageSize=computed(()=>view.value==='grid'?9:24)
const criteria=computed(()=>new URLSearchParams(Object.entries({...filters,game:game.value,size:pageSize.value}).filter(([,v])=>v!=='')).toString())
const lot=()=>new URLSearchParams({edition:edition.value,condition:condition.value,tradable:tradable.value}).toString()
const editionName=v=>languages[v] || uiText('미지정')
const conditionName=v=>v==='UNSPECIFIED'?uiText('미지정'):v
const lotBusy=ref(false),lotReady=ref(false)
let lotVersion=0
async function readLot(){
  if(!selected.value)return
  const generation=++lotVersion;lotBusy.value=true;lotReady.value=false;formError.value=''
  try{
    const row=await session.authenticatedRequest('/me/binder/'+selected.value.id+'?'+lot())
    if(generation!==lotVersion||!selected.value)return
    lotReady.value=true;selected.value.expected=row.quantity;quantity.value=Math.max(1,row.quantity)
  }catch(cause){if(generation===lotVersion)formError.value=cause.message}
  finally{if(generation===lotVersion)lotBusy.value=false}
}
watch(criteria,()=>{page.value=0},{flush:'sync'})
watch([()=>session.account?.email,retry],async([email],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort());stats.value=[]
  if(!email)return
  try{const rows=await session.authenticatedRequest('/me/binder/stats',{signal:abort.signal});if(!abort.signal.aborted)stats.value=rows}
  catch(cause){if(!abort.signal.aborted)error.value=cause.message}
},{immediate:true})
let returnFocus
watch(game, () => { page.value = 0; selected.value = null },{flush:'sync'})
watch([() => session.account?.email, criteria, page, retry, locale], async ([email], _, cleanup) => {
  const abort = new AbortController(); cleanup(() => abort.abort())
  error.value = ''; result.value = null
  if (!email) { selected.value = null; return }
  try {
    const [options, list] = await Promise.all([request('/games',{signal:abort.signal}),
      session.authenticatedRequest('/me/binder?'+criteria.value+'&page='+page.value+'&lang='+locale.value,{signal:abort.signal})])
    if (!abort.signal.aborted) { games.value = options; result.value = list }
  } catch (cause) { if (!abort.signal.aborted) error.value = cause.message }
}, {immediate:true})
watch([() => session.account?.email, () => route.query.card], async ([email,card], _, cleanup) => {
  selected.value = null
  if (!email || !/^\d+$/.test(card || '')) return
  const abort = new AbortController(); cleanup(() => abort.abort())
  try {
    const item = await request('/cards/'+card+'?lang='+locale.value,{signal:abort.signal})
    if (!abort.signal.aborted) await pick(item)
  } catch (cause) { if (!abort.signal.aborted) error.value = cause.message }
}, {immediate:true})
async function open(item,count,initial,trigger) {
  if(trigger) returnFocus=trigger
  lotVersion++;lotBusy.value=false;lotReady.value=true;edition.value=item.edition||'und';condition.value=item.condition||'UNSPECIFIED';tradable.value=!!item.tradable
  selected.value={...item,id:item.cardId ?? item.id,expected:count}
  quantity.value=initial
  formError.value=''
  await nextTick()
  if(!quantityDialog.value)return
  if(!quantityDialog.value.open)quantityDialog.value.showModal()
  quantityInput.value.focus()
  quantityInput.value.select()
}
watch(locale,async(lang,_,cleanup)=>{
  const item=selected.value
  if(!item)return
  const abort=new AbortController();cleanup(()=>abort.abort())
  try{
    const card=await request('/cards/'+item.id+'?lang='+lang,{signal:abort.signal})
    if(!abort.signal.aborted && selected.value===item)Object.assign(item,{name:card.name,language:card.language,nameBasis:card.nameBasis,nameReferenceUrl:card.nameReferenceUrl})
  }catch(cause){if(!abort.signal.aborted&&selected.value===item)formError.value=cause.message}
})
function close() {
  lotVersion++;lotBusy.value=false
  quantityDialog.value?.close()
  selected.value=null
  const trigger=returnFocus
  returnFocus=null
  nextTick(()=>{ if(trigger?.isConnected)trigger.focus({preventScroll:true}) })
}
async function pick(item,trigger) {
  if (busy.value) return
  const email=session.account?.email
  busy.value=true; error.value=''; notice.value=''
  try {
    const { quantity:count }=await session.authenticatedRequest('/me/binder/'+item.id)
    if (email===session.account?.email) {
      busy.value=false
      await open(item,count,Math.min(9999,count+1),trigger)
    }
  } catch(cause) { error.value=cause.message }
  finally { busy.value=false }
}
async function save() {
  const card=selected.value
  if (!card || busy.value || !lotReady.value || lotBusy.value) return
  busy.value=true; formError.value=''
  try {
    await session.authenticatedRequest('/me/binder/'+card.id+'?'+lot(),{method:'PUT',body:{quantity:quantity.value,expectedQuantity:card.expected}})
    notice.value=quantity.value ? card.name+' '+quantity.value+uiText("장을 저장했습니다.") : card.name+uiText(" 카드를 바인더에서 뺐습니다.")
    close()
    if (page.value && result.value?.items.length===1 && !quantity.value) page.value--
    else retry.value++
  } catch(cause) {
    if(cause.status===409) {
      const current=await session.authenticatedRequest('/me/binder/'+card.id+'?'+lot()).catch(()=>null)
      if(current) {card.expected=current.quantity;quantity.value=current.quantity}
      else lotReady.value=false
      retry.value++
    }
    formError.value=cause.message
  } finally { busy.value=false }
}
</script>
<template>
  <LibraryAccess :title="$t('내 바인더')">
    <header class="lib-heading"><h1>{{ $t("내 바인더") }}</h1><RouterLink to="/decks">{{ $t("내 덱") }}</RouterLink></header>
    <label class="lib-filter">{{ $t("게임") }}<select v-model="game"><option value="">{{ $t("전체 게임") }}</option><option v-for="g in games" :value="g.code" :key="g.code">{{ gameName(g.code,g.name) }}</option></select></label>
    <details class="lib-panel binder-filters"><summary>{{ $t("바인더 필터") }}</summary><div class="binder-fields">
      <label>{{ $t("카드 이름·번호") }}<input v-model="filters.q" type="search" maxlength="100"></label><label>{{ $t("레어도") }}<input v-model="filters.rarity" maxlength="64"></label>
      <label>{{ $t("최소 수량") }}<input type="number" min="1" max="9999" v-model="filters.minQuantity"></label><label>{{ $t("최대 수량") }}<input type="number" min="1" max="9999" v-model="filters.maxQuantity"></label>
      <label>{{ $t("언어판") }}<select v-model="filters.edition"><option value="">{{ $t("전체") }}</option><option v-for="v in editions" :key="v" :value="v">{{ editionName(v) }}</option></select></label>
      <label>{{ $t("카드 상태") }}<select v-model="filters.condition"><option value="">{{ $t("전체") }}</option><option v-for="v in conditions" :key="v" :value="v">{{ conditionName(v) }}</option></select></label>
      <label>{{ $t("거래 가능") }}<select v-model="filters.tradable"><option value="">{{ $t("전체") }}</option><option value="true">{{ $t("가능") }}</option><option value="false">{{ $t("불가") }}</option></select></label>
      </div></details>
    <details v-if="stats.length" class="lib-panel"><summary>{{ $t("종목별 보유 현황") }}</summary><ul class="binder-stats"><li v-for="row in stats" :key="row.gameCode">{{gameName(row.gameCode)}} <span>{{row.uniqueCards}}{{ $t("종 ·") }} {{row.copies}}{{ $t("장") }}</span></li></ul></details>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ $t("새로고침") }}</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <dialog v-if="selected" ref="quantityDialog" class="lib-dialog" aria-labelledby="binder-card-title" @cancel.prevent="!busy && close()">
      <form @submit.prevent="save">
        <h2 id="binder-card-title" :lang="selected.language || ''">{{ selected.name }}</h2><CardTextCredit :card="selected"/>
        <label>{{ $t("보유 수량") }}<input ref="quantityInput" v-model.number="quantity" type="number" required min="0" max="9999" inputmode="numeric" autofocus :readonly="busy" aria-describedby="binder-quantity-help" /></label>
        <div class="binder-fields"><label>{{ $t("언어판") }}<select v-model="edition" :disabled="busy" @change="readLot"><option v-for="v in editions" :key="v" :value="v">{{ editionName(v) }}</option></select></label>
         <label>{{ $t("카드 상태") }}<select v-model="condition" :disabled="busy" @change="readLot"><option v-for="v in conditions" :key="v" :value="v">{{ conditionName(v) }}</option></select></label>
         <label><input type="checkbox" v-model="tradable" :disabled="busy" @change="readLot">{{ $t("거래 가능") }}</label></div>
        <p id="binder-quantity-help" class="muted">{{ $t('선택한 언어판·상태·거래 여부의 수량입니다. 0으로 저장하면 해당 항목을 뺍니다.') }}</p>
        <p v-if="formError" role="alert" class="inline-error">{{ formError }}</p>
        <div class="lib-actions"><button class="primary" :disabled="busy || lotBusy || !lotReady">{{ $t("수량 저장") }}</button><button class="secondary" type="button" :disabled="busy" @click="close">{{ $t("취소") }}</button></div>
      </form>
    </dialog>
    <div class="library-grid">
      <section class="lib-panel" :aria-label="$t('보유 카드')">
        <h2>{{ $t("보유 카드") }} <small v-if="result">{{ result.total }}{{ $t("종 ·") }} {{ result.copies }}{{ $t("장") }}</small></h2>
        <div class="view-control" role="group" :aria-label="$t('보기 방식')"><button class="secondary" :aria-pressed="view==='grid'" @click="view='grid'">{{ $t("9포켓") }}</button><button class="secondary" :aria-pressed="view==='list'" @click="view='list'">{{ $t("목록") }}</button></div>
        <p v-if="!result && !error" role="status">{{ $t("바인더를 불러오는 중입니다.") }}</p>
        <p v-else-if="result && !result.items.length">{{ $t("이 바인더에 등록된 카드가 없습니다.") }}</p>
        <ul v-else-if="result" class="lib-list" :class="{'binder-pockets':view==='grid'}"><li v-for="card in result.items" :key="[card.cardId,card.edition,card.condition,card.tradable].join('-')">
          <div class="lib-print"><LibraryThumbnail placeholder :image="card.image" :src="card.imageUrl" :language="card.imageLanguage" :printing="card" v-slot="{art}"><div>
            <RouterLink :to="{name:'card',params:{id:card.cardId},query:{lang:locale}}" :lang="card.language || ''">{{ card.name }}</RouterLink>
            <CardTextCredit :card="card"/><small>{{ [card.number,card.rarity,editionName(card.edition),conditionName(card.condition),card.tradable?$t('거래 가능'):''].filter(Boolean).join(' · ') }}</small>
            <small v-if="art?.reference"><ArtworkCredit :language="art.language" :printing="card"/></small>
          </div></LibraryThumbnail></div>
          <button class="secondary" :disabled="busy" :aria-label="card.name+$t(' 수량 수정')" @click="open(card,card.quantity,card.quantity,$event.currentTarget)">{{ card.quantity }}{{ $t("장 수정") }}</button>
        </li></ul>
        <nav v-if="result?.total>pageSize" class="pagination" :aria-label="$t('바인더 페이지')"><button class="secondary" :disabled="!page" @click="page--">{{ $t("이전") }}</button><span>{{ page+1 }} / {{ Math.ceil(result.total/pageSize) }}</span><button class="secondary" :disabled="(page+1)*pageSize>=result.total" @click="page++">{{ $t("다음") }}</button></nav>
      </section>
      <CatalogPicker :game="game" :disabled="busy" @pick="pick" />
    </div>
  </LibraryAccess>
</template>

<style scoped>
.binder-fields { display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));gap:.7rem;margin:.75rem 0; }
.binder-fields input:not([type=checkbox]),.binder-fields select {width:100%;padding:.45rem;border:1px solid var(--bd);border-radius:6px;color:var(--tx);background:var(--sf)}
.binder-stats {list-style:none;padding:0}.binder-stats li{display:flex;justify-content:space-between;border-bottom:1px solid var(--bd);padding:.4rem 0}
.view-control{display:flex;gap:.25rem;margin:.7rem 0}.view-control [aria-pressed=true]{border-color:var(--ac);color:var(--ac)}
.binder-pockets {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--bd);border:1px solid var(--bd)}
.binder-pockets>li {display:flex;align-items:stretch;justify-content:space-between;flex-direction:column;min-width:0;background:var(--sf);padding:.4rem;overflow-wrap:anywhere}
.binder-pockets .lib-print {display:flex;flex-direction:column;align-items:start}.binder-pockets :deep(.lib-thumbnail){align-self:center;flex:none;width:min(100%,clamp(88px,24vw,152px));height:auto;aspect-ratio:300/438}
</style>
