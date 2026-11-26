<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useSession } from '../stores/session'
import { gameCodes, gameName, t } from '../i18n'

defineProps({disabled:Boolean})
const emit=defineEmits(['saving','saved'])
const session=useSession()
const account=ref(''), game=ref(''), store=ref(null), query=ref(''), page=ref(0), retry=ref(0)
const rows=ref([]), loading=ref(false), searchError=ref(''), saving=ref(false), error=ref(''), handleInput=ref(null)
const username=computed(()=>account.value.trim().replace(/^@/,''))
const term=computed(()=>query.value.trim())
const awaitingStore=computed(()=>!store.value && Boolean(term.value))
const pageSize=50
watch(term,()=>{page.value=0},{flush:'sync'})
watch([term,page,retry,store],([value,index,,chosen],_,cleanup)=>{
  rows.value=[];searchError.value='';loading.value=Boolean(value && !chosen)
  if (!value || chosen) return
  const controller=new AbortController()
  const timer=setTimeout(async()=>{
    try {
      const params=new URLSearchParams({q:value,page:String(index)})
      const result=await session.adminRequest('/stores?'+params,{signal:controller.signal})
      if(!controller.signal.aborted) rows.value=result
    } catch(cause) {
      if(!controller.signal.aborted) searchError.value=cause.message
    } finally {
      if(!controller.signal.aborted) loading.value=false
    }
  },180)
  cleanup(()=>{clearTimeout(timer);controller.abort()})
})
function choose(event) {
  const selected=rows.value.find(row=>String(row.id)===event.target.value)
  if(selected){store.value=selected;query.value='';page.value=0}
}
async function subscribe() {
  if(saving.value || !session.isAdmin || session.adminAccessBlocked || awaitingStore.value) return
  error.value=''
  if(!/^[A-Za-z0-9_]{1,15}$/.test(username.value)){
    error.value=t('X 사용자명은 영문·숫자·밑줄로 1~15자입니다.')
    handleInput.value?.focus()
    return
  }
  saving.value=true
  emit('saving',true)
  try {
    await session.adminRequest('/sources/x',{method:'POST',body:{username:username.value,gameCode:game.value || null,storeId:store.value?.id ?? null}})
    const handle=username.value
    account.value='';game.value='';store.value=null;query.value=''
    emit('saved',handle)
  } catch(cause) {
    if(cause.status===409){error.value=t('이미 등록된 X 계정입니다.');nextTick(()=>handleInput.value?.focus())}
    else error.value=cause.status===400?t('X 사용자명과 선택한 게임·매장을 확인해 주세요.'):cause.message
  } finally { saving.value=false;emit('saving',false) }
}
</script>

<template>
  <details class="ops-card x-source">
    <summary>{{ $t('X 계정 구독') }}</summary>
    <form @submit.prevent="subscribe">
      <fieldset :disabled="saving || disabled">
        <label for="source-username">{{ $t('X 사용자명') }}</label>
        <input id="source-username" ref="handleInput" v-model="account" type="text" required maxlength="16"
          placeholder="@username" autocomplete="off" autocapitalize="none" spellcheck="false">
        <label for="source-game">{{ $t('게임') }}</label>
        <select id="source-game" v-model="game">
          <option value="">{{ $t('공통 · 게임 미지정') }}</option>
          <option v-for="code in gameCodes" :value="code" :key="code">{{ gameName(code) }}</option>
        </select>
        <div v-if="store" class="selected-store"><strong>{{ store.name }}</strong><span>{{store.address}}</span>
          <button type="button" class="text-button" @click="store=null">{{ $t('매장 연결 해제') }}</button>
        </div>
        <template v-else>
          <label for="source-store-search">{{ $t('연결할 매장 (선택)') }}</label>
          <input id="source-store-search" v-model="query" type="search" maxlength="100" :placeholder="$t('매장명 또는 도로명')">
          <template v-if="term">
            <p v-if="loading" role="status">{{ $t('매장을 찾고 있습니다.') }}</p>
            <p v-else-if="searchError" role="alert">{{ searchError }} <button type="button" class="text-button" @click="retry++">{{ $t('다시 시도') }}</button></p>
            <p v-else-if="!rows.length">{{ $t('검색 결과가 없습니다.') }}</p>
            <template v-else>
              <label for="source-store-choice">{{ $t('매장 선택') }}</label>
              <select id="source-store-choice" value="" @change="choose"><option value="" disabled>{{ $t('검색 결과에서 선택') }}</option>
                <option v-for="row in rows" :key="row.id" :value="row.id">{{ row.name }} · {{ row.address }}</option>
              </select>
            </template>
            <nav v-if="!loading && (page || rows.length===pageSize)" class="pagination" :aria-label="$t('매장 목록 페이지')">
              <button type="button" class="secondary" :disabled="!page" @click="page--">{{ $t('이전') }}</button>
              <span>{{ page+1 }}</span><button type="button" class="secondary" :disabled="rows.length<pageSize" @click="page++">{{ $t('다음') }}</button>
            </nav>
            <button type="button" class="text-button" @click="query=''">{{ $t('매장 연결 안 함') }}</button>
          </template>
        </template>
        <p class="muted">{{ $t('이 계정에서 수집한 소식은 검수 대기열에 들어갑니다.') }}</p>
        <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
        <button class="primary" :disabled="saving || disabled || awaitingStore">{{ $t('구독 추가') }}</button>
      </fieldset>
    </form>
  </details>
</template>

<style scoped>
.x-source{margin:0 0 1rem}.x-source summary{font-weight:650;min-height:32px;align-content:center}
.x-source fieldset{min-width:0;margin:.6rem 0 0;padding:0;border:0;max-width:34rem}
.x-source fieldset>label{display:block;margin:.6rem 0 .2rem;font-weight:600}
.x-source input,.x-source select{display:block;min-height:44px;width:100%;padding:.45rem;background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:6px}
.x-source p{margin:.6rem 0;font-size:.9rem}.x-source fieldset>button{min-height:44px}
.selected-store{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem .7rem;margin:.8rem 0}.selected-store span{color:var(--mu)}
</style>
