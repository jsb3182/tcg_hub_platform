<script setup>
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import LibraryAccess from '../components/LibraryAccess.vue'
import CatalogPicker from '../components/CatalogPicker.vue'
import LibraryThumbnail from '../components/LibraryThumbnail.vue'
const session = useSession(), route = useRoute()
const games = ref([]), game = ref(''), page = ref(0), result = ref(null), error = ref(''), notice = ref('')
const selected = ref(null), quantity = ref(1), busy = ref(false), retry = ref(0)
const quantityDialog = ref(null), quantityInput = ref(null), formError = ref('')
let returnFocus
watch(game, () => { page.value = 0; selected.value = null },{flush:'sync'})
watch([() => session.account?.email, game, page, retry], async ([email], _, cleanup) => {
  const abort = new AbortController(); cleanup(() => abort.abort())
  error.value = ''; result.value = null
  if (!email) { selected.value = null; return }
  try {
    const [options, list] = await Promise.all([request('/games',{signal:abort.signal}),
      session.authenticatedRequest('/me/binder?'+new URLSearchParams({game:game.value,page:page.value}),{signal:abort.signal})])
    if (!abort.signal.aborted) { games.value = options; result.value = list }
  } catch (cause) { if (!abort.signal.aborted) error.value = cause.message }
}, {immediate:true})
watch([() => session.account?.email, () => route.query.card], async ([email,card], _, cleanup) => {
  selected.value = null
  if (!email || !/^\d+$/.test(card || '')) return
  const abort = new AbortController(); cleanup(() => abort.abort())
  try {
    const item = await request('/cards/'+card,{signal:abort.signal})
    if (!abort.signal.aborted) await pick(item)
  } catch (cause) { if (!abort.signal.aborted) error.value = cause.message }
}, {immediate:true})
async function open(item,count,initial,trigger) {
  if(trigger) returnFocus=trigger
  selected.value={id:item.cardId ?? item.id, name:item.name, expected:count}
  quantity.value=initial
  formError.value=''
  await nextTick()
  if(!quantityDialog.value)return
  if(!quantityDialog.value.open)quantityDialog.value.showModal()
  quantityInput.value.focus()
  quantityInput.value.select()
}
function close() {
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
  if (!card || busy.value) return
  busy.value=true; formError.value=''
  try {
    await session.authenticatedRequest('/me/binder/'+card.id,{method:'PUT',body:{quantity:quantity.value,expectedQuantity:card.expected}})
    notice.value=quantity.value ? card.name+' '+quantity.value+'장을 저장했습니다.' : card.name+' 카드를 바인더에서 뺐습니다.'
    close()
    if (page.value && result.value?.items.length===1 && !quantity.value) page.value--
    else retry.value++
  } catch(cause) {
    if(cause.status===409) {
      const current=await session.authenticatedRequest('/me/binder/'+card.id).catch(()=>null)
      if(current) await open(card,current.quantity,current.quantity)
      retry.value++
    }
    formError.value=cause.message
  } finally { busy.value=false }
}
</script>
<template>
  <LibraryAccess title="내 바인더">
    <header class="lib-heading"><h1>내 바인더</h1><RouterLink to="/decks">내 덱</RouterLink></header>
    <label class="lib-filter">게임<select v-model="game"><option value="">전체 게임</option><option v-for="g in games" :value="g.code" :key="g.code">{{ g.name }}</option></select></label>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button class="text-button" @click="retry++">새로고침</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <dialog v-if="selected" ref="quantityDialog" class="lib-dialog" aria-labelledby="binder-card-title" @cancel.prevent="!busy && close()">
      <form @submit.prevent="save">
        <h2 id="binder-card-title">{{ selected.name }}</h2>
        <label>보유 수량<input ref="quantityInput" v-model.number="quantity" type="number" required min="0" max="9999" inputmode="numeric" autofocus :readonly="busy" aria-describedby="binder-quantity-help" /></label>
        <p id="binder-quantity-help" class="muted">0장으로 저장하면 바인더에서 빠집니다.</p>
        <p v-if="formError" role="alert" class="inline-error">{{ formError }}</p>
        <div class="lib-actions"><button class="primary" :disabled="busy">수량 저장</button><button class="secondary" type="button" :disabled="busy" @click="close">취소</button></div>
      </form>
    </dialog>
    <div class="library-grid">
      <section class="lib-panel" aria-label="보유 카드">
        <h2>보유 카드 <small v-if="result">{{ result.total }}종 · {{ result.copies }}장</small></h2>
        <p v-if="!result && !error" role="status">바인더를 불러오는 중입니다.</p>
        <p v-else-if="result && !result.items.length">이 바인더에 등록된 카드가 없습니다.</p>
        <ul v-else-if="result" class="lib-list"><li v-for="card in result.items" :key="card.cardId">
          <div class="lib-print"><LibraryThumbnail :image="card.image" /><div><RouterLink :to="'/cards/'+card.cardId">{{ card.name }}</RouterLink><small>{{ [card.number,card.packName].filter(Boolean).join(' · ') }}</small></div></div>
          <button class="secondary" :disabled="busy" :aria-label="card.name+' 수량 수정'" @click="open(card,card.quantity,card.quantity,$event.currentTarget)">{{ card.quantity }}장 수정</button>
        </li></ul>
        <nav v-if="result?.total>24" class="pagination" aria-label="바인더 페이지"><button class="secondary" :disabled="!page" @click="page--">이전</button><span>{{ page+1 }} / {{ Math.ceil(result.total/24) }}</span><button class="secondary" :disabled="(page+1)*24>=result.total" @click="page++">다음</button></nav>
      </section>
      <CatalogPicker :game="game" :disabled="busy" @pick="pick" />
    </div>
  </LibraryAccess>
</template>
