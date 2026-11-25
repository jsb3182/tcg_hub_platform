<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import { savedDate,stateLabel } from '../library'
import { practiceLanguage } from '../play'
import LibraryAccess from '../components/LibraryAccess.vue'
const session=useSession(), page=ref(0), result=ref(null), games=ref([]), error=ref(''), retry=ref(0)
const route=useRoute()
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
  <LibraryAccess title="내 덱"><header class="lib-heading"><h1>내 덱</h1><RouterLink class="primary" :to="{name:'deck-new',query}">새 덱 만들기</RouterLink></header>
    <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">다시 시도</button></p>
    <p v-else-if="!result" role="status">덱을 불러오는 중입니다.</p>
    <p v-else-if="!result.total" class="state">첫 덱을 만들어 도감의 카드를 담아 보세요.</p>
    <ul v-else class="lib-panel lib-list"><li v-for="d in result.items" :key="d.id"><div>
      <RouterLink :to="{name:'deck-edit',params:{id:d.id},query}">{{ d.name }}</RouterLink>
      <small>{{ games.find(g=>g.code===d.gameCode)?.name || d.gameCode }} · {{ d.cards }}장 · {{ stateLabel(d.state) }} · {{ d.shareToken?'링크 공유 중':'비공개' }}</small>
      <small>저장 {{ savedDate(d.updatedAt) }}</small></div></li></ul>
    <nav v-if="result?.total>24" class="pagination" aria-label="내 덱 페이지"><button class="secondary" :disabled="!page" @click="page--">이전</button><span>{{ page+1 }} / {{ Math.ceil(result.total/24) }}</span><button class="secondary" :disabled="(page+1)*24>=result.total" @click="page++">다음</button></nav>
  </LibraryAccess>
</template>
