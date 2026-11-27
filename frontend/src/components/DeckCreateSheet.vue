<script setup>
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {useRouter} from 'vue-router'
import {useSession} from '../stores/session'
import {locale,gameCodes,gameName,t} from '../i18n'
import {sectionLabel} from '../library'
import {pt} from '../pack'
import {prepareDeckPicture,storeDeckPictures} from '../deckPictures'
import DeckBanner from './DeckBanner.vue'
import CaptureReview from './CaptureReview.vue'
const props=defineProps({game:String,ordinal:Number}),router=useRouter(),session=useSession()
const panel=ref(null),chosenGame=ref(''),name=ref(''),nameEn=ref(''),nameJa=ref(''),entries=ref([]),rule=ref(null),ruleRetry=ref(0)
const pending=ref(false),busy=ref(false),cover=ref(null),preview=ref(''),error=ref(''),created=ref(null),open=ref(false)
const emit=defineEmits(['closed'])
const validEntries=computed(()=>entries.value.every(e=>Number.isInteger(e.quantity)&&e.quantity>=1&&e.quantity<=999))
const deck=computed(()=>({name:name.value.trim()||pt('새 덱'),nameEn:nameEn.value,nameJa:nameJa.value,gameCode:chosenGame.value,entries:entries.value,cards:entries.value.reduce((n,e)=>n+e.quantity,0)}))
function clearCover(){if(preview.value)URL.revokeObjectURL(preview.value);preview.value='';cover.value=null}
function show(){clearCover();name.value='';nameJa.value='';nameEn.value='';entries.value=[];error.value='';created.value=null;pending.value=false;chosenGame.value=props.game||'YUGIOH';open.value=true;panel.value.showModal()}
function close(){if(busy.value)return;if(!created.value && (name.value||nameJa.value||nameEn.value||entries.value.length||cover.value||pending.value) && !window.confirm(pt('저장하지 않은 변경을 취소할까요?')))return;panel.value.close()}
function closed(){open.value=false;clearCover();emit('closed')}
function addRows(rows){
  for(const row of rows){
    const same=entries.value.find(e=>e.cardId===row.cardId && e.section===row.section &&
      (e.variantId??null)===(row.variantId??null) && (e.neuronArtwork??null)===(row.neuronArtwork??null))
    if(same)same.quantity+=row.quantity
    else entries.value.push({...row})
  }
}
function submittedEntries(){
  const combined=new Map()
  for(const {cardId,section,quantity,variantId,neuronArtwork} of entries.value){
    const key=[cardId,section,variantId,neuronArtwork].join('/')
    if(combined.has(key))combined.get(key).quantity+=quantity
    else combined.set(key,{cardId,section,quantity,variantId,neuronArtwork})
  }
  return [...combined.values()]
}
defineExpose({show})
watch([open,chosenGame,ruleRetry],async([active,g],_,clean)=>{
  rule.value=null;if(!active)return
  const abort=new AbortController();clean(()=>abort.abort());error.value=''
  try{const result=await session.authenticatedRequest('/me/decks/rules/'+g,{signal:abort.signal});if(!abort.signal.aborted)rule.value=result}
  catch(e){if(!abort.signal.aborted)error.value=e.message}
})
onBeforeUnmount(clearCover)
async function picture(event){
  const file=event.target.files[0];if(!file)return
  try{const jpeg=await prepareDeckPicture(file,'cover');if(!open.value)return;clearCover();cover.value=jpeg;preview.value=URL.createObjectURL(jpeg)}
  catch{error.value=pt('이미지를 읽지 못했습니다.')}finally{event.target.value=''}
}
async function create(){
  if(busy.value||pending.value||!name.value.trim()||!rule.value||!validEntries.value)return
  busy.value=true;error.value=''
  try{
    if(!created.value)created.value=await session.authenticatedRequest('/me/decks',{method:'POST',body:{name:name.value.trim(),nameJa:nameJa.value.trim(),nameEn:nameEn.value.trim(),gameCode:chosenGame.value,revision:0,state:'DRAFT',shared:false,
      entries:submittedEntries()}})
    if(cover.value)await storeDeckPictures(session,created.value.id,{cover:cover.value})
    panel.value.close();await router.push({name:'deck-edit',params:{id:created.value.id},query:{lang:locale.value}})
  }catch(e){error.value=created.value?pt('덱은 저장됐습니다. 이미지를 다시 저장하세요.'):e.message}
  finally{busy.value=false}
}
</script>
<template><dialog ref="panel" class="create-sheet" :aria-label="pt('새 덱 추가')" @close="closed" @cancel.prevent="close">
  <section v-if="open"><header><div><h2>{{ pt('새 덱 추가') }}</h2><small v-if="ordinal">{{ ordinal }} · {{ pt('새 덱') }}</small></div><button type="button" class="secondary" :aria-label="pt('닫기')" @click="close">×</button></header>
  <div class="sheet-fields"><label>{{ pt('게임') }}<select v-model="chosenGame" :disabled="pending||!!entries.length||busy||!!created"><option v-for="g in gameCodes" :key="g" :value="g">{{ gameName(g) }}</option></select></label>
    <label>{{ pt('한국어 이름 (필수)') }}<input v-model="name" lang="ko" required maxlength="100" :disabled="!!created||busy"></label>
    <label>{{ pt('일본어 이름') }}<input v-model="nameJa" lang="ja" maxlength="100" :disabled="!!created||busy"></label>
    <label>{{ pt('영어 이름') }}<input v-model="nameEn" lang="en" maxlength="100" :disabled="!!created||busy"></label>
    <details v-if="!created"><summary>{{ pt('덱 레시피 캡처') }}</summary><CaptureReview v-if="rule" :game="chosenGame" :zones="rule.sections.map(s=>s.section)" @pending="v=>pending=v" @apply="addRows" @suggest="v=>{if(!name)name=v}"/></details>
    <details v-if="entries.length && rule && !created" class="staged-cards" open>
      <summary>{{ pt('확인한 카드') }} · {{ entries.length }}</summary>
      <div v-for="(row,i) in entries" :key="i"><strong>{{ row.name || row.number }} <small>{{ row.number }}</small></strong>
        <label>{{ t('구역') }}<select v-model="row.section" :disabled="busy"><option v-for="s in rule.sections" :key="s.section" :value="s.section">{{ sectionLabel(s.section) }}</option></select></label>
        <label>{{ t('수량') }}<input type="number" v-model.number="row.quantity" min="1" max="999" :disabled="busy"></label>
        <button class="text-button" type="button" :disabled="busy" @click="entries.splice(i,1)">{{ t('이 항목 제외') }}</button>
      </div>
    </details>
    <label>{{ pt('대표 이미지') }}<input type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy" @change="picture"></label>
    <DeckBanner :deck="deck" :image="preview" :ordinal="ordinal"/>
    <p v-if="error" role="alert">{{ error }} <button v-if="!rule" class="text-button" @click="ruleRetry++">{{ pt('다시 시도') }}</button></p>
  </div><footer><button class="secondary" :disabled="busy" @click="close">{{ pt('취소') }}</button><button class="primary" :disabled="busy||pending||!rule||!validEntries||!name.trim()" @click="create">{{ pt(created?'다시 시도':'만들기') }}</button></footer>
  </section></dialog></template>
<style scoped>
.staged-cards>div{display:flex;gap:7px;flex-wrap:wrap;align-items:end;padding:.55rem 0;border-top:1px solid var(--bd)}.staged-cards strong{flex-basis:100%;overflow-wrap:anywhere}.staged-cards strong small{color:var(--mu);font-weight:400}.staged-cards label{display:grid;min-width:0;font-size:.8rem}.staged-cards input,.staged-cards select{min-height:40px;max-width:9rem}.staged-cards input{width:4.4rem}
.create-sheet{margin:auto auto 0;width:min(560px,100%);max-width:100%;max-height:88vh;padding:0;border:1px solid var(--bd);border-radius:18px 18px 0 0;background:var(--sf);color:var(--tx)}.create-sheet::backdrop{background:rgb(12 18 30/.45)}
.create-sheet header,.create-sheet footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:var(--sf);position:sticky;z-index:1}.create-sheet header{top:0;border-bottom:1px solid var(--bd)}.create-sheet header h2{margin:0;font-size:1.25rem}.create-sheet header button{border-radius:50%;min-width:40px;min-height:40px}.create-sheet footer{bottom:0;border-top:1px solid var(--bd);padding-bottom:max(12px,env(safe-area-inset-bottom))}.create-sheet footer button{flex:1}
.sheet-fields{display:grid;gap:.8rem;padding:14px 16px}.sheet-fields>label{display:grid;gap:3px;font-size:.88rem}.sheet-fields>label :is(input,select){min-width:0;width:100%;min-height:42px;padding:.4rem .6rem;border:1px solid var(--bd);border-radius:6px;background:var(--sf);color:var(--tx)}.sheet-fields>details>summary{cursor:pointer;min-height:44px;padding-block:9px}
</style>
