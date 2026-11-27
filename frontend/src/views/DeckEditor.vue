<script setup>
import { t as uiText, gameName, locale } from '../i18n'

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import { useSession } from '../stores/session'
import { sectionLabel, savedDate, stateLabel } from '../library'
import { practiceLanguage } from '../play'
import LibraryAccess from '../components/LibraryAccess.vue'
import CatalogPicker from '../components/CatalogPicker.vue'
import DeckRecipe from '../components/DeckRecipe.vue'
import CaptureReview from '../components/CaptureReview.vue'
import DeckPictures from '../components/DeckPictures.vue'
import DeckNeeds from '../components/DeckNeeds.vue'
import {storeDeckPictures} from '../deckPictures'
const route=useRoute(), router=useRouter(), session=useSession()
const games=ref([]), game=ref(''), name=ref(''), section=ref('MAIN'), entries=ref([]), saved=ref(null), rule=ref(null)
const shared=ref(false), loading=ref(true), busy=ref(false), error=ref(''), notice=ref(''), reload=ref(0)
const history=ref(null), historyPage=ref(0), historyBusy=ref(false), historyError=ref(''), failedLoad=ref(false)
const id=computed(()=>route.params.id), selectedGameName=computed(()=>gameName(game.value))
const shareUrl=computed(()=>saved.value?.shareToken ? location.origin+'/shared/decks/'+saved.value.shareToken : '')
const baseline=ref(null), practiceChoice=ref(null), errorElement=ref(null)
const nameJa=ref(''),nameEn=ref(''),pictures=ref({}),reviewing=ref(false)
const undone=ref([]),redone=ref([])
function snapshotEntries(){return entries.value.map(e=>({...e}))}
function beforeCardEdit(){undone.value.push(snapshotEntries());if(undone.value.length>30)undone.value.shift();redone.value=[]}
function restoreCards(from,to){if(from.length){to.push(snapshotEntries());entries.value=from.pop()}}
function updateQuantity(entry,event){
  const value=event.target.value===''?'':Number(event.target.value)
  if(value!==entry.quantity){beforeCardEdit();entry.quantity=value}
}
function removeEntry(entry){beforeCardEdit();entries.value.splice(entries.value.indexOf(entry),1)}
let retryPictures=null
const content=computed(()=>JSON.stringify([name.value,nameJa.value,nameEn.value,game.value,shared.value,
  entries.value.map(e=>[e.cardId,e.section,e.quantity,e.variantId,e.neuronArtwork])]))
const dirty=computed(()=>baseline.value!==null && (baseline.value!==content.value||reviewing.value||Object.keys(pictures.value).length>0))
const preview=computed(()=>({name:name.value || uiText("이름 없는 덱"),nameJa:nameJa.value,nameEn:nameEn.value,gameCode:game.value,entries:entries.value,rule:rule.value,state:
  saved.value && !dirty.value ? saved.value.state : 'DRAFT'}))
let generation=0
let approvedPractice=''
function mayDiscard() {
  return !dirty.value || (!busy.value && window.confirm(uiText("저장하지 않은 덱 변경 사항을 버리고 이동할까요?")))
}
onBeforeRouteLeave(to=>to.fullPath===approvedPractice || mayDiscard())
onBeforeRouteUpdate((to,from)=>{
  if(to.name!==from.name || to.params.id!==from.params.id ||
    (to.name==='deck-new' && (to.query.card!==from.query.card || to.query.game!==from.query.game)))return mayDiscard()
})
function beforeUnload(event) {
  event.preventDefault()
  event.returnValue=''
}
function beforeLogout(event) { if(!mayDiscard())event.preventDefault() }
watch(dirty,changed=>{
  if(changed)window.addEventListener('beforeunload',beforeUnload)
  else window.removeEventListener('beforeunload',beforeUnload)
},{flush:'sync'})
onMounted(()=>window.addEventListener('tcg-before-logout',beforeLogout))
onBeforeUnmount(()=>{
  window.removeEventListener('beforeunload',beforeUnload)
  window.removeEventListener('tcg-before-logout',beforeLogout)
})
function fill(deck) {
  undone.value=[];redone.value=[]
  saved.value=deck;rule.value=deck.rule;game.value=deck.gameCode;name.value=deck.name
  nameJa.value=deck.nameJa||'';nameEn.value=deck.nameEn||''
  entries.value=deck.entries.map(e=>({...e}));shared.value=!!deck.shareToken
  baseline.value=content.value
  if (!rule.value.sections.some(s=>s.section===section.value)) section.value=rule.value.sections[0]?.section
}
watch([()=>session.account?.email,id,()=>route.name,reload,
  ()=>route.name==='deck-new'?route.query.card:null,()=>route.name==='deck-new'?route.query.game:null],async([email,deckId,routeName],_,cleanup)=>{
  const current=++generation, abort=new AbortController();cleanup(()=>abort.abort())
  baseline.value=null;loading.value=true;error.value='';notice.value='';saved.value=null;rule.value=null;entries.value=[];history.value=null;historyError.value=''
  failedLoad.value=false;name.value='';nameJa.value='';nameEn.value='';shared.value=false;reviewing.value=false
  undone.value=[];redone.value=[]
  pictures.value=retryPictures?.id===String(deckId)?retryPictures.files:{}
  if(Object.keys(pictures.value).length)error.value=uiText('덱은 저장됐습니다. 남은 이미지를 다시 저장하세요.')
  retryPictures=null
  if(!email || !['deck-edit','deck-new'].includes(routeName))return
  try {
    const options=await request('/games',{signal:abort.signal})
    if(current!==generation)return
    games.value=options
    if(deckId){
      const deck=await session.authenticatedRequest('/me/decks/'+deckId+'?lang='+locale.value,{signal:abort.signal})
      if(current===generation)fill(deck)
    }else{
      const preferred=options.find(g=>g.code===route.query.game) || options.find(g=>g.code==='YUGIOH') || options[0]
      game.value=preferred.code
      await loadRule(current,abort.signal)
      if(current!==generation)return
      baseline.value=content.value
      if(current===generation && /^\d+$/.test(route.query.card || '')){
        const card=await request('/cards/'+route.query.card+'?lang='+practiceLanguage(route.query.lang),{signal:abort.signal})
        if(current===generation && card.gameCode===game.value)add(card)
      }
    }
  }catch(cause){if(!abort.signal.aborted){error.value=cause.message;failedLoad.value=true}}
  finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})
watch(locale,async(lang,_,cleanup)=>{
  if(!id.value||!saved.value)return
  const abort=new AbortController(),current=generation;cleanup(()=>abort.abort())
  try{
    const deck=await session.authenticatedRequest('/me/decks/'+id.value+'?lang='+lang,{signal:abort.signal})
    if(current!==generation||abort.signal.aborted)return
    const names=new Map(deck.entries.map(entry=>[entry.cardId,entry.name]))
    entries.value.forEach(entry=>{if(names.has(entry.cardId))entry.name=names.get(entry.cardId)})
  }catch(cause){if(!abort.signal.aborted&&current===generation)error.value=cause.message}
})
async function loadRule(current,signal) {
  const result=await session.authenticatedRequest('/me/decks/rules/'+encodeURIComponent(game.value),{signal})
  if(current===generation){rule.value=result;section.value=result.sections[0]?.section}
}
async function switchGame(e) {
  game.value=e.target.value;rule.value=null;error.value='';busy.value=true
  try{await loadRule(generation)}catch(cause){error.value=cause.message}finally{busy.value=false}
}
function add(card) {
  beforeCardEdit()
  const item=entries.value.find(e=>e.cardId===card.id && e.section===section.value && e.variantId==null&&e.neuronArtwork==null)
  if(item)item.quantity=Math.min(999,item.quantity+1)
  else entries.value.push({cardId:card.id,name:card.name,number:card.number,packName:card.packName,section:section.value,quantity:1,
    curveValue:card.curveValue ?? null,imageUrl:card.imageUrl,image:card.image ?? card.variants?.find(v=>v.image)?.image ?? null,
    type:card.type||card.specs?.type||[card.specs?.k,card.specs?.sub].filter(Boolean).join(' · ')})
  notice.value=sectionLabel(section.value)+uiText("에 ")+card.name+uiText(" 추가")
}
function importRows(rows) {
  beforeCardEdit()
  for(const row of rows){
    const neuronArtwork=row.variantId==null?(row.neuronArtwork??null):null
    const existing=entries.value.find(e=>e.cardId===row.cardId&&e.section===row.section&&(e.variantId??null)===(row.variantId??null)&&(e.neuronArtwork??null)===neuronArtwork)
    if(existing)existing.quantity+=row.quantity
    else entries.value.push({...row,neuronArtwork})
  }
  notice.value=uiText('캡처에서 확인한 카드를 추가했습니다.')
}
async function showError(message) {
  error.value=message
  await nextTick()
  errorElement.value?.focus()
}
const languageQuery=computed(()=>({lang:practiceLanguage(route.query.lang)}))
const practiceRoute=deck=>({name:'play',query:{deck:deck.id,game:deck.gameCode,...languageQuery.value}})
async function save(state,practice=false) {
  if(busy.value)return
  practiceChoice.value?.close()
  error.value='';notice.value=''
  if(reviewing.value)return showError(uiText('캡처 검토를 마치고 확인한 카드를 덱에 추가하세요.'))
  if(!name.value.trim())return showError(uiText("덱 이름을 입력해 주세요."))
  if(entries.value.some(e=>!Number.isInteger(e.quantity)||e.quantity<1||e.quantity>999))return showError(uiText("카드 수량은 1~999 사이의 정수로 입력해 주세요."))
  const current=generation,wasNew=!id.value
  busy.value=true
  try {
    const deck=await session.authenticatedRequest('/me/decks'+(id.value?'/'+id.value:''),{method:id.value?'PUT':'POST',body:{
      name:name.value.trim(),state,gameCode:game.value,shared:shared.value,revision:saved.value?.revision??0,
      nameJa:nameJa.value.trim(),nameEn:nameEn.value.trim(),entries:entries.value.map(({cardId,quantity,section,variantId,neuronArtwork})=>({cardId,quantity,section,variantId,neuronArtwork}))}})
    if(current!==generation)return
    fill(deck);history.value=null
    let mediaFailed=false
    try {await storeDeckPictures(session,deck.id,pictures.value)}
    catch {mediaFailed=true;if(wasNew){retryPictures={id:String(deck.id),files:{...pictures.value}};pictures.value={}}}
    if(wasNew)await router.replace({name:'deck-edit',params:{id:deck.id},query:languageQuery.value})
    if(mediaFailed){error.value=uiText('덱은 저장됐습니다. 남은 이미지를 다시 저장하세요.');return}
    if(practice){await router.push(practiceRoute(deck));return}
    notice.value=stateLabel(state)+uiText(" 상태로 저장했습니다.")
  }catch(cause){if(current===generation)await showError(cause.message)}
  finally{busy.value=false}
}
function practice() {
  if(!saved.value)return save('DRAFT',true)
  if(!dirty.value)return router.push(practiceRoute(saved.value))
  practiceChoice.value?.showModal()
}
async function useSaved() {
  const to=practiceRoute(saved.value)
  practiceChoice.value.close()
  approvedPractice=router.resolve(to).fullPath
  try{await router.push(to)}finally{approvedPractice=''}
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
    if(current===generation){beforeCardEdit();name.value=snapshot.name;nameJa.value=snapshot.nameJa||'';nameEn.value=snapshot.nameEn||'';entries.value=snapshot.entries.map(e=>({...e}));notice.value=rev+uiText("번째 구성을 편집기에 불러왔습니다. 저장하면 새 내역으로 기록됩니다.")}
  }catch(cause){if(current===generation)historyError.value=cause.message}
  finally{historyBusy.value=false}
}
const exportedCode=ref('')
async function exportCode(){
  try{
    const result=await session.authenticatedRequest('/me/decks/'+id.value+'/code')
    exportedCode.value=result.code
  }catch(cause){await showError(cause.message)}
}
watch(id,()=>{exportedCode.value=''})
async function copyLink() {
  try{await navigator.clipboard.writeText(shareUrl.value);notice.value=uiText("공유 링크를 복사했습니다.")}
  catch{notice.value=uiText("공유 주소를 길게 눌러 복사해 주세요.")}
}
</script>
<template>
  <LibraryAccess :title="$t('덱 편집')"><header class="lib-heading"><h1>{{ id?$t("덱 편집"):$t("새 덱") }}</h1><RouterLink :to="{name:'decks',query:languageQuery}">{{ $t("내 덱 목록") }}</RouterLink></header>
    <details v-if="saved" class="lib-panel deck-code"><summary>{{ $t("덱 코드 내보내기") }}</summary><button class="secondary" @click="exportCode">{{ $t("저장본 코드 보기") }}</button><label v-if="exportedCode">{{ $t("덱 코드") }}<textarea readonly rows="3" :value="exportedCode" @focus="$event.target.select()"/></label></details>
    <p v-if="error" ref="errorElement" tabindex="-1" role="alert" class="inline-error">{{ error }} <button class="text-button" @click="mayDiscard() && reload++">{{ $t("저장된 구성 다시 불러오기") }}</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">{{ $t("덱을 불러오는 중입니다.") }}</p>
    <div v-else-if="!failedLoad" class="lib-editor"><div class="library-grid">
      <section class="lib-panel"><fieldset :disabled="busy"><label>{{ $t("덱 이름") }}<input v-model="name" maxlength="100" :placeholder="$t('덱 이름')" /></label>
        <div class="deck-alias-fields"><label>{{ $t("일본어 이름") }}<input v-model="nameJa" maxlength="100" lang="ja"/></label><label>{{ $t("영어 이름") }}<input v-model="nameEn" maxlength="100" lang="en"/></label></div>
        <label>{{ $t("게임") }}<select :value="game" :disabled="!!id || entries.length>0 || reviewing" @change="switchGame"><option v-for="g in games" :key="g.code" :value="g.code">{{ gameName(g.code,g.name) }}</option></select></label>
        <CaptureReview v-if="game==='YUGIOH'&&rule" @apply="importRows" @pending="reviewing=$event" @suggest="v=>{if(!name)name=v}"/>
        <DeckPictures :id="id" :pictures="pictures" :disabled="busy" @pick="(slot,file)=>pictures={...pictures,[slot]:file}"/>
        <template v-if="rule"><p>{{ $t("기본 구성 규칙 · 버전") }} {{ rule.version }} <a v-if="rule.source" :href="rule.source" target="_blank" rel="noopener noreferrer">{{ $t("공식 규칙") }}</a></p>
          <p class="muted">{{ $t("구역별 장수와 중복 수량을 검사합니다. 금지·제한 목록과 개별 카드 예외는 대회 규정을 확인해 주세요.") }}</p>
          <p v-if="game==='YUGIOH'"><a href="https://www.yugioh.co.kr/site/limit_regulation.php" target="_blank" rel="noopener noreferrer">{{ $t('한국 OCG 금지·제한 목록') }}</a></p>
          <div class="lib-actions"><button type="button" class="text-button" :disabled="!undone.length" @click="restoreCards(undone,redone)">{{ $t("카드 변경 취소") }}</button><button type="button" class="text-button" :disabled="!redone.length" @click="restoreCards(redone,undone)">{{ $t("카드 변경 다시 적용") }}</button></div>
          <section v-for="s in rule.sections" :key="s.section"><h2>{{ sectionLabel(s.section) }}
            <small>{{ entries.filter(e=>e.section===s.section).reduce((n,e)=>n+(Number(e.quantity)||0),0) }}{{ $t("장 · 규칙") }} {{ s.minCards ?? 0 }}{{ s.maxCards===s.minCards?'':'~'+(s.maxCards ?? $t("제한 없음")) }}{{ $t("장") }}</small>
          </h2>
          <ul class="lib-list"><li v-for="e in entries.filter(e=>e.section===s.section)" :key="[e.cardId,e.variantId,e.neuronArtwork].join('-')"><div><strong>{{ e.name }}</strong><small>{{ [e.number,e.packName,e.neuronArtwork&&($t('일러스트')+' '+e.neuronArtwork)].filter(Boolean).join(' · ') }}</small></div>
            <div class="lib-controls"><input :value="e.quantity" @change="updateQuantity(e,$event)" type="number" min="1" max="999" :aria-label="e.name+$t(' 수량')" /><button type="button" class="text-button" :aria-label="e.name+$t(' 빼기')" @click="removeEntry(e)">{{ $t("빼기") }}</button></div>
          </li></ul></section>
          <label class="lib-check"><input type="checkbox" v-model="shared" />{{ $t("링크가 있는 사람에게 덱 공개") }}</label>
          <div class="lib-actions"><button type="button" class="secondary" @click="save('DRAFT')">{{ $t("임시 저장") }}</button><button type="button" class="primary" @click="save('COMPLETE')">{{ $t("구성 완료 저장") }}</button></div>
          <p v-if="dirty" class="lib-unsaved" role="status">{{ $t("저장되지 않은 변경 사항이 있습니다.") }}</p>
        </template></fieldset>
        <div v-if="shareUrl"><p><a :href="shareUrl">{{ shareUrl }}</a></p><button class="secondary" @click="copyLink">{{ $t("공유 링크 복사") }}</button></div>
        <button v-if="rule && ['YUGIOH','POKEMON','ONEPIECE'].includes(game)" type="button" class="secondary" :disabled="busy || (!saved && !entries.length)" @click="practice">{{ saved?$t("이 덱으로 연습"):$t("임시 저장 후 연습") }}</button>
        <dialog ref="practiceChoice" class="lib-dialog" aria-labelledby="practice-choice-title">
          <h2 id="practice-choice-title">{{ $t("어떤 구성으로 연습할까요?") }}</h2>
          <p>{{ $t("저장하지 않은 변경 사항이 있습니다.") }}</p>
          <div class="lib-dialog-actions">
            <button class="primary" @click="save(saved.state,true)">{{ $t("변경 저장 후 연습") }}</button>
            <button class="secondary" @click="useSaved">{{ $t("변경 버리고 저장본으로 연습") }}</button>
            <button class="text-button" autofocus @click="practiceChoice.close()">{{ $t("편집 계속") }}</button>
          </div>
        </dialog>
      </section>
      <div v-if="rule"><label class="lib-filter">{{ $t("카드를 넣을 구역") }}<select v-model="section"><option v-for="s in rule.sections" :value="s.section" :key="s.section">{{ sectionLabel(s.section) }}</option></select></label>
        <CatalogPicker :game="game" :disabled="busy" @pick="add" /></div>
    </div>
    <DeckRecipe v-if="rule" :deck="preview" :game-name="selectedGameName" />
    <DeckNeeds v-if="saved" :deck-id="saved.id" :revision="saved.revision"/>
    <section v-if="saved" class="lib-panel"><div class="lib-heading"><h2>{{ $t("저장 내역") }}</h2><button class="secondary" :disabled="historyBusy" @click="loadHistory()">{{ $t("내역 조회") }}</button></div>
      <p v-if="historyError" role="alert">{{ historyError }}</p><p v-if="history && !history.items.length">{{ $t("이 덱의 첫 변경부터 내역을 기록합니다.") }}</p>
      <ul v-if="history" class="lib-list"><li v-for="h in history.items" :key="h.revision"><div>{{ h.name }} <small>{{ h.revision }}{{ $t("번째 ·") }} {{ savedDate(h.savedAt) }} · {{ h.cards }}{{ $t("장 ·") }} {{ stateLabel(h.state) }}</small></div>
        <button class="secondary" :disabled="historyBusy||busy" @click="applyRevision(h.revision)">{{ $t("편집기에 불러오기") }}</button></li></ul>
      <nav v-if="history?.total>24" class="pagination" :aria-label="$t('덱 저장 내역 페이지')"><button :disabled="!historyPage || historyBusy" @click="loadHistory(historyPage-1)">{{ $t("이전") }}</button><span>{{ historyPage+1 }} / {{ Math.ceil(history.total/24) }}</span><button :disabled="(historyPage+1)*24>=history.total || historyBusy" @click="loadHistory(historyPage+1)">{{ $t("다음") }}</button></nav>
    </section></div>
  </LibraryAccess>
</template>
