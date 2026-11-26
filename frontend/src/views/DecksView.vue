<script setup>
import {gameName} from '../i18n'
import { computed, ref, watch } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import { savedDate,stateLabel } from '../library'
import { practiceLanguage } from '../play'
import LibraryAccess from '../components/LibraryAccess.vue'
const session=useSession(), page=ref(0), result=ref(null), games=ref([]), error=ref(''), retry=ref(0)
const route=useRoute(),router=useRouter(),code=ref(''),importing=ref(false),importError=ref('')
async function importDeck(){
  if(importing.value||!code.value.trim())return
  importing.value=true;importError.value=''
  try{
    const deck=await session.authenticatedRequest('/me/decks/import',{method:'POST',body:{code:code.value.trim()}})
    await router.push({name:'deck-edit',params:{id:deck.id},query:query.value})
  }catch(cause){importError.value=cause.message}finally{importing.value=false}
}
const query=computed(()=>({lang:practiceLanguage(route.query.lang)}))
watch([()=>session.account?.email,page,retry],async ([email],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  result.value=null;error.value=''
  if(!email)return
  try {
    const [list,options]=await Promise.all([session.authenticatedRequest('/me/decks?page='+page.value,{signal:abort.signal}),request('/games',{signal:abort.signal})])
    if(!abort.signal.aborted){result.value=list;games.value=options}
  } catch(cause){if(!abort.signal.aborted)error.value=cause.message}
},{immediate:true})
</script>
<template>
  <LibraryAccess :title="$t('내 덱')"><header class="lib-heading"><h1>{{ $t("내 덱") }}</h1><RouterLink class="primary" :to="{name:'deck-new',query}">{{ $t("새 덱 만들기") }}</RouterLink></header>
    <details class="lib-panel deck-code"><summary>{{ $t("덱 코드 가져오기") }}</summary><form @submit.prevent="importDeck"><label>{{ $t("덱 코드") }}<textarea v-model="code" required maxlength="100000" rows="3"/></label><button class="primary" :disabled="importing || !code.trim()">{{ $t("새 덱으로 가져오기") }}</button><p v-if="importError" role="alert">{{ importError }}</p></form></details>
    <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
    <p v-else-if="!result" role="status">{{ $t("덱을 불러오는 중입니다.") }}</p>
    <p v-else-if="!result.total" class="state">{{ $t("첫 덱을 만들어 도감의 카드를 담아 보세요.") }}</p>
    <ul v-else class="lib-panel lib-list"><li v-for="d in result.items" :key="d.id"><div>
      <RouterLink :to="{name:'deck-edit',params:{id:d.id},query}">{{ d.name }}</RouterLink>
      <small>{{ gameName(d.gameCode) }} · {{ d.cards }}{{ $t("장 ·") }} {{ stateLabel(d.state) }} · {{ d.shareToken?$t("링크 공유 중"):$t("비공개") }}</small>
      <small>{{ $t("저장") }} {{ savedDate(d.updatedAt) }}</small></div></li></ul>
    <nav v-if="result?.total>24" class="pagination" :aria-label="$t('내 덱 페이지')"><button class="secondary" :disabled="!page" @click="page--">{{ $t("이전") }}</button><span>{{ page+1 }} / {{ Math.ceil(result.total/24) }}</span><button class="secondary" :disabled="(page+1)*24>=result.total" @click="page++">{{ $t("다음") }}</button></nav>
  </LibraryAccess>
</template>
