<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import { sectionLabel, savedDate, stateLabel } from '../library'
import LibraryAccess from '../components/LibraryAccess.vue'
import CatalogPicker from '../components/CatalogPicker.vue'
import DeckRecipe from '../components/DeckRecipe.vue'
const route=useRoute(), router=useRouter(), session=useSession()
const games=ref([]), game=ref(''), name=ref(''), section=ref('MAIN'), entries=ref([]), saved=ref(null), rule=ref(null)
const shared=ref(false), loading=ref(true), busy=ref(false), error=ref(''), notice=ref(''), reload=ref(0)
const history=ref(null), historyPage=ref(0), historyBusy=ref(false), historyError=ref(''), failedLoad=ref(false)
const id=computed(()=>route.params.id), gameName=computed(()=>games.value.find(g=>g.code===game.value)?.name)
const shareUrl=computed(()=>saved.value?.shareToken ? location.origin+'/shared/decks/'+saved.value.shareToken : '')
const preview=computed(()=>({name:name.value || '이름 없는 덱',gameCode:game.value,entries:entries.value,rule:rule.value,state:
  saved.value && saved.value.name===name.value && JSON.stringify(entries.value)===JSON.stringify(saved.value.entries) ? saved.value.state : 'DRAFT'}))
let generation=0
function fill(deck) {
  saved.value=deck;rule.value=deck.rule;game.value=deck.gameCode;name.value=deck.name
  entries.value=deck.entries.map(e=>({...e}));shared.value=!!deck.shareToken
  if (!rule.value.sections.some(s=>s.section===section.value)) section.value=rule.value.sections[0]?.section
}
watch([()=>session.account?.email,id,()=>route.name,reload],async([email,deckId,routeName],_,cleanup)=>{
  const current=++generation, abort=new AbortController();cleanup(()=>abort.abort())
  loading.value=true;error.value='';notice.value='';saved.value=null;rule.value=null;entries.value=[];history.value=null;historyError.value=''
  failedLoad.value=false;name.value='';shared.value=false
  if(!email || !['deck-edit','deck-new'].includes(routeName))return
  try {
    const options=await request('/games',{signal:abort.signal})
    if(current!==generation)return
    games.value=options
    if(deckId){
      const deck=await session.authenticatedRequest('/me/decks/'+deckId,{signal:abort.signal})
      if(current===generation)fill(deck)
    }else{
      const preferred=options.find(g=>g.code===route.query.game) || options.find(g=>g.code==='YUGIOH') || options[0]
      game.value=preferred.code
      await loadRule(current,abort.signal)
      if(current===generation && /^\d+$/.test(route.query.card || '')){
        const card=await request('/cards/'+route.query.card,{signal:abort.signal})
        if(current===generation && card.gameCode===game.value)add(card)
      }
    }
  }catch(cause){if(!abort.signal.aborted){error.value=cause.message;failedLoad.value=true}}
  finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})
async function loadRule(current,signal) {
  const result=await session.authenticatedRequest('/me/decks/rules/'+encodeURIComponent(game.value),{signal})
  if(current===generation){rule.value=result;section.value=result.sections[0]?.section}
}
async function switchGame(e) {
  game.value=e.target.value;rule.value=null;error.value='';busy.value=true
  try{await loadRule(generation)}catch(cause){error.value=cause.message}finally{busy.value=false}
}
function add(card) {
  const item=entries.value.find(e=>e.cardId===card.id && e.section===section.value)
  if(item)item.quantity=Math.min(999,item.quantity+1)
  else entries.value.push({cardId:card.id,name:card.name,number:card.number,packName:card.packName,section:section.value,quantity:1})
  notice.value=sectionLabel(section.value)+'에 '+card.name+' 추가'
}
async function save(state) {
  error.value='';notice.value=''
  if(!name.value.trim()){error.value='덱 이름을 입력해 주세요.';return}
  if(entries.value.some(e=>!Number.isInteger(e.quantity)||e.quantity<1||e.quantity>999)){error.value='카드 수량은 1~999 사이의 정수로 입력해 주세요.';return}
  const current=generation,wasNew=!id.value
  busy.value=true
  try {
    const deck=await session.authenticatedRequest('/me/decks'+(id.value?'/'+id.value:''),{method:id.value?'PUT':'POST',body:{
      name:name.value.trim(),state,gameCode:game.value,shared:shared.value,revision:saved.value?.revision??0,
      entries:entries.value.map(({cardId,quantity,section})=>({cardId,quantity,section}))}})
    if(current!==generation)return
    if(wasNew)await router.replace({name:'deck-edit',params:{id:deck.id}})
    else {fill(deck);history.value=null}
    notice.value=stateLabel(state)+' 상태로 저장했습니다.'
  }catch(cause){if(current===generation)error.value=cause.message}
  finally{busy.value=false}
}
async function loadHistory(page=0) {
  const current=generation
  historyBusy.value=true;historyError.value=''
  try{
    const result=await session.authenticatedRequest('/me/decks/'+id.value+'/history?page='+page)
    if(current===generation){history.value=result;historyPage.value=page}
  }catch(cause){if(current===generation)historyError.value=cause.message}
  finally{historyBusy.value=false}
}
async function applyRevision(rev) {
  const current=generation
  historyBusy.value=true;historyError.value=''
  try{
    const snapshot=await session.authenticatedRequest('/me/decks/'+id.value+'/history/'+rev)
    if(current===generation){name.value=snapshot.name;entries.value=snapshot.entries.map(e=>({...e}));notice.value=rev+'번째 구성을 편집기에 불러왔습니다. 저장하면 새 내역으로 기록됩니다.'}
  }catch(cause){if(current===generation)historyError.value=cause.message}
  finally{historyBusy.value=false}
}
async function copyLink() {
  try{await navigator.clipboard.writeText(shareUrl.value);notice.value='공유 링크를 복사했습니다.'}
  catch{notice.value='공유 주소를 길게 눌러 복사해 주세요.'}
}
</script>
<template>
  <LibraryAccess title="덱 편집"><header class="lib-heading"><h1>{{ id?'덱 편집':'새 덱' }}</h1><RouterLink to="/decks">내 덱 목록</RouterLink></header>
    <p v-if="error" role="alert" class="inline-error">{{ error }} <button class="text-button" @click="reload++">저장된 구성 다시 불러오기</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">덱을 불러오는 중입니다.</p>
    <div v-else-if="!failedLoad" class="lib-editor"><div class="library-grid">
      <section class="lib-panel"><fieldset :disabled="busy"><label>덱 이름<input v-model="name" maxlength="100" placeholder="덱 이름" /></label>
        <label>게임<select :value="game" :disabled="!!id || entries.length>0" @change="switchGame"><option v-for="g in games" :key="g.code" :value="g.code">{{ g.name }}</option></select></label>
        <template v-if="rule"><p>기본 구성 규칙 · 버전 {{ rule.version }} <a v-if="rule.source" :href="rule.source" target="_blank" rel="noopener noreferrer">공식 규칙</a></p>
          <p class="muted">구역별 장수와 중복 수량을 검사합니다. 금지·제한 목록과 개별 카드 예외는 대회 규정을 확인해 주세요.</p>
          <section v-for="s in rule.sections" :key="s.section"><h2>{{ sectionLabel(s.section) }}
            <small>{{ entries.filter(e=>e.section===s.section).reduce((n,e)=>n+(Number(e.quantity)||0),0) }}장 · 규칙 {{ s.minCards ?? 0 }}{{ s.maxCards===s.minCards?'':'~'+(s.maxCards ?? '제한 없음') }}장</small>
          </h2>
          <ul class="lib-list"><li v-for="e in entries.filter(e=>e.section===s.section)" :key="e.cardId"><div><strong>{{ e.name }}</strong><small>{{ [e.number,e.packName].filter(Boolean).join(' · ') }}</small></div>
            <div class="lib-controls"><input v-model.number="e.quantity" type="number" min="1" max="999" :aria-label="e.name+' 수량'" /><button type="button" class="text-button" :aria-label="e.name+' 빼기'" @click="entries.splice(entries.indexOf(e),1)">빼기</button></div>
          </li></ul></section>
          <label class="lib-check"><input type="checkbox" v-model="shared" />링크가 있는 사람에게 덱 공개</label>
          <div class="lib-actions"><button type="button" class="secondary" @click="save('DRAFT')">임시 저장</button><button type="button" class="primary" @click="save('COMPLETE')">구성 완료 저장</button></div>
        </template></fieldset>
        <div v-if="shareUrl"><p><a :href="shareUrl">{{ shareUrl }}</a></p><button class="secondary" @click="copyLink">공유 링크 복사</button></div>
        <RouterLink v-if="saved && ['YUGIOH','POKEMON'].includes(game)" :to="{name:'play',query:{deck:id,game}}">이 덱으로 연습</RouterLink>
      </section>
      <div v-if="rule"><label class="lib-filter">카드를 넣을 구역<select v-model="section"><option v-for="s in rule.sections" :value="s.section" :key="s.section">{{ sectionLabel(s.section) }}</option></select></label>
        <CatalogPicker :game="game" :disabled="busy" @pick="add" /></div>
    </div>
    <DeckRecipe v-if="rule" :deck="preview" :game-name="gameName" />
    <section v-if="saved" class="lib-panel"><div class="lib-heading"><h2>저장 내역</h2><button class="secondary" :disabled="historyBusy" @click="loadHistory()">내역 조회</button></div>
      <p v-if="historyError" role="alert">{{ historyError }}</p><p v-if="history && !history.items.length">이 덱의 첫 변경부터 내역을 기록합니다.</p>
      <ul v-if="history" class="lib-list"><li v-for="h in history.items" :key="h.revision"><div>{{ h.name }} <small>{{ h.revision }}번째 · {{ savedDate(h.savedAt) }} · {{ h.cards }}장 · {{ stateLabel(h.state) }}</small></div>
        <button class="secondary" :disabled="historyBusy||busy" @click="applyRevision(h.revision)">편집기에 불러오기</button></li></ul>
      <nav v-if="history?.total>24" class="pagination" aria-label="덱 저장 내역 페이지"><button :disabled="!historyPage || historyBusy" @click="loadHistory(historyPage-1)">이전</button><span>{{ historyPage+1 }} / {{ Math.ceil(history.total/24) }}</span><button :disabled="(historyPage+1)*24>=history.total || historyBusy" @click="loadHistory(historyPage+1)">다음</button></nav>
    </section></div>
  </LibraryAccess>
</template>
