<script setup>
import {gameName, t} from '../i18n'
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { useSession } from '../stores/session'
import { savedDate,stateLabel } from '../library'
import { practiceLanguage } from '../play'
import LibraryAccess from '../components/LibraryAccess.vue'
import DeckNeeds from '../components/DeckNeeds.vue'
const session=useSession(), page=ref(0), result=ref(null), error=ref(''), retry=ref(0)
const search=ref(''), covers=ref({}), exporting=ref(false), exportError=ref('')
const exportController=new AbortController()
onBeforeUnmount(()=>exportController.abort())
async function download(format){
  exporting.value=true;exportError.value=''
  try{const {exportDecks}=await import('../deckExport');await exportDecks(session,format,exportController.signal)}
  catch{if(!exportController.signal.aborted)exportError.value=t('덱 파일을 저장하지 못했습니다. 다시 시도해 주세요.')}
  finally{exporting.value=false}
}
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
watch(search,()=>{page.value=0},{flush:'sync'})
watch([()=>session.account?.email,page,retry,search],([email],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  result.value=null;error.value='';covers.value={}
  if(!email)return
  const timer=setTimeout(async()=>{
  try {
    const args=new URLSearchParams({page:String(page.value),q:search.value.trim()})
    const list=await session.authenticatedRequest('/me/decks?'+args,{signal:abort.signal})
    if(abort.signal.aborted)return
    result.value=list
    for(const d of list.items.filter(v=>v.hasCover)){
      try{const cover=await session.authenticatedRequest('/me/decks/'+d.id+'/decoration/cover',{signal:abort.signal})
        if(!abort.signal.aborted)covers.value[d.id]=cover.image
      }catch{if(abort.signal.aborted)return}
    }
  } catch(cause){if(!abort.signal.aborted)error.value=cause.message}
  },search.value?160:0)
  cleanup(()=>clearTimeout(timer))
},{immediate:true})
</script>
<template>
  <LibraryAccess :title="$t('내 덱')"><header class="lib-heading"><h1>{{ $t("내 덱") }}</h1><RouterLink class="primary" :to="{name:'deck-new',query}">{{ $t("새 덱 만들기") }}</RouterLink></header>
    <div class="decks-overview"><label>{{ $t('내 덱 검색') }}<input v-model="search" type="search" maxlength="120" :placeholder="$t('덱 이름, 카드명 또는 코드')"/></label>
      <span v-if="result" role="status">{{ $t('덱') }} {{ result.total }} · {{ $t('카드') }} {{ (result.totalCards??0).toLocaleString() }}{{ $t('장') }}</span></div>
    <details class="lib-panel deck-code"><summary>{{ $t("덱 코드 가져오기") }}</summary><form @submit.prevent="importDeck"><label>{{ $t("덱 코드") }}<textarea v-model="code" required maxlength="100000" rows="3"/></label><button class="primary" :disabled="importing || !code.trim()">{{ $t("새 덱으로 가져오기") }}</button><p v-if="importError" role="alert">{{ importError }}</p></form></details>
    <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
    <p v-else-if="!result" role="status">{{ $t("덱을 불러오는 중입니다.") }}</p>
    <p v-else-if="!result.total" class="state">{{ search ? $t('조건에 맞는 덱이 없습니다.') : $t("첫 덱을 만들어 도감의 카드를 담아 보세요.") }}</p>
    <ul v-else class="lib-panel lib-list"><li v-for="d in result.items" :key="d.id"><div>
      <RouterLink :to="{name:'deck-edit',params:{id:d.id},query}">{{ d.name }}</RouterLink>
      <small v-if="d.nameJa||d.nameEn">{{ [d.nameJa,d.nameEn].filter(Boolean).join(' · ') }}</small>
      <small v-if="d.gameCode==='YUGIOH'">{{ $t('메인') }} {{ d.mainCount }} · {{ $t('엑스트라') }} {{ d.extraCount }} · {{ $t('사이드') }} {{ d.sideCount }}</small>
      <small>{{ gameName(d.gameCode) }} · {{ d.cards }}{{ $t("장 ·") }} {{ stateLabel(d.state) }} · {{ d.shareToken?$t("링크 공유 중"):$t("비공개") }}</small>
      <small>{{ $t("저장") }} {{ savedDate(d.updatedAt) }}</small></div><img v-if="covers[d.id]" :src="covers[d.id]" class="deck-cover" alt=""></li></ul>
    <nav v-if="result?.total>24" class="pagination" :aria-label="$t('내 덱 페이지')"><button class="secondary" :disabled="!page" @click="page--">{{ $t("이전") }}</button><span>{{ page+1 }} / {{ Math.ceil(result.total/24) }}</span><button class="secondary" :disabled="(page+1)*24>=result.total" @click="page++">{{ $t("다음") }}</button></nav>
    <div v-if="result?.total||search" class="lib-actions"><strong>{{ $t('내 덱 데이터 내보내기') }}</strong><button type="button" class="secondary" :disabled="exporting" @click="download('json')">JSON</button><button type="button" class="secondary" :disabled="exporting" @click="download('xlsx')">Excel</button></div>
    <p v-if="exportError" role="alert">{{ exportError }}</p>
    <DeckNeeds v-if="result?.total"/>
  </LibraryAccess>
</template>
<style scoped>.decks-overview{display:flex;flex-wrap:wrap;gap:1rem;align-items:end;justify-content:space-between}.decks-overview label{display:grid;gap:.25rem;min-width:min(18rem,100%)}.decks-overview span{color:var(--mu)}.deck-cover{width:clamp(5rem,20vw,12rem);height:auto;max-height:5.5rem;object-fit:cover;border-radius:4px}</style>
