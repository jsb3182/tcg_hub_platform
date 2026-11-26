<script setup>
import { ref, watch } from 'vue'
import { useSession } from '../stores/session'
const props = defineProps({game:String, packId:Number, packName:String, disabled:Boolean})
const emit = defineEmits(['select'])
const session = useSession()
const query = ref(''), page = ref(0), items = ref([]), total = ref(0), error = ref(''), loading = ref(false), retry = ref(0)
const pageSize = 12
watch(()=>props.game,()=>{query.value=''; page.value=0},{flush:'sync'})
watch(query,()=>{page.value=0},{flush:'sync'})
watch([()=>props.game,query,page,retry],([game],_,cleanup)=>{
  const controller = new AbortController()
  items.value=[];total.value=0;error.value='';loading.value=!!game
  const timer=setTimeout(async()=>{
    if (!game) return
    try {
      const params = new URLSearchParams({game,q:query.value.trim(),page:page.value,size:pageSize})
      const result = await session.adminRequest('/catalog/packs?'+params,{signal:controller.signal})
      if (!controller.signal.aborted) { items.value=result.items; total.value=result.total }
    } catch (cause) { if (!controller.signal.aborted) error.value=cause.message }
    finally { if (!controller.signal.aborted) loading.value=false }
  },query.value?200:0)
  cleanup(()=>{clearTimeout(timer);controller.abort()})
},{immediate:true})
function select(event) {
  const selected = items.value.find(p=>p.id===Number(event.target.value))
  emit('select',selected?.id ?? null,selected?.name ?? '')
}
</script>
<template>
  <fieldset class="catalog-pack-select" :disabled="disabled || !game">
    <legend>{{ $t("수록 팩") }}</legend>
    <label>{{ $t("팩 검색") }}<input v-model="query" type="search" maxlength="120" :placeholder="$t('팩 이름 또는 코드')" /></label>
    <label>{{ $t("연결할 팩") }}<select :value="packId ?? ''" @change="select">
      <option value="">{{ $t("팩 없음") }}</option>
      <option v-if="packId && !items.some(p=>p.id===packId)" :value="packId">{{ packName || $t("팩 #")+packId }}</option>
      <option v-for="p in items" :value="p.id" :key="p.id">{{ p.name }}{{ p.code?' · '+p.code:'' }}</option>
    </select></label>
    <p v-if="loading" class="muted" role="status">{{ $t("팩 검색 중…") }}</p>
    <p v-else-if="error" role="alert">{{ error }} <button type="button" class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
    <p v-else-if="query && !total" class="muted">{{ $t("검색 결과가 없습니다.") }}</p>
    <nav v-if="total>pageSize" class="pagination" :aria-label="$t('연결할 팩 페이지')">
      <button type="button" class="secondary" :disabled="!page" @click="page--">{{ $t("이전") }}</button><span>{{ page+1 }} / {{ Math.ceil(total/pageSize) }}</span>
      <button type="button" class="secondary" :disabled="(page+1)*pageSize>=total" @click="page++">{{ $t("다음") }}</button>
    </nav>
  </fieldset>
</template>
