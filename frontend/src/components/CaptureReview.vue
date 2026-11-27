<script setup>
import { computed,onBeforeUnmount,ref,watch } from 'vue'
import { locale,t } from '../i18n'
import { sectionLabel } from '../library'
import { request } from '../api'
import CatalogPicker from './CatalogPicker.vue'
import LibraryThumbnail from './LibraryThumbnail.vue'
import CardTextCredit from './CardTextCredit.vue'
import {localizedCards,nameFields} from '../cardLabels'
const emit=defineEmits(['apply','suggest','pending'])
const input=ref(null), rows=ref([]),error=ref(''),busy=ref(false), active=ref(null), search=ref(false), progress=ref('')
const sections=['MAIN','EXTRA','SIDE']
const counts=computed(()=>Object.fromEntries(sections.map(s=>[s,rows.value.filter(r=>r.section===s).reduce((n,r)=>n+(Number(r.quantity)||0),0)])))
const pending=computed(()=>rows.value.reduce((n,r)=>n+(r.confirmed?0:Number(r.quantity)||0),0))
const validRows=computed(()=>rows.value.length>0&&rows.value.every(r=>r.selected&&r.confirmed&&Number.isInteger(r.quantity)&&r.quantity>=1&&r.quantity<=999))
const reviewIds=computed(()=>[...new Set(rows.value.flatMap(row=>row.candidates.map(c=>c.cardId)))].join(','))
const labels=ref(new Map()),labelError=ref(''),labelRetry=ref(0)
watch([reviewIds,locale,labelRetry],async([ids,lang],previous,cleanup)=>{
  if(!ids || previous?.[1]!==lang)labels.value=new Map()
  labelError.value=''
  if(!ids)return
  const missing=ids.split(',').map(Number).filter(id=>!labels.value.has(id))
  if(!missing.length)return
  const abort=new AbortController();cleanup(()=>abort.abort())
  try{
    const result=await localizedCards(missing,'YUGIOH',lang,abort.signal)
    if(!abort.signal.aborted)labels.value=new Map([...labels.value,...result])
  }catch(e){if(!abort.signal.aborted)labelError.value=e.message}
})
function caption(card){return labels.value.get(card?.cardId) || card}
let control=null
onBeforeUnmount(()=>control?.abort())
function cancel(){control?.abort();control=null;busy.value=false;rows.value=[];error.value='';active.value=null;search.value=false;if(input.value)input.value.value='';emit('pending',false)}
async function read(event) {
  const file=event.target.files[0]
  if(!file)return
  cancel()
  const job=new AbortController();control=job;busy.value=true;progress.value='';emit('pending',true)
  try {
    const { recognizeRecipeCapture }=await import('../recipeCapture')
    const result=await recognizeRecipeCapture(file,{game:'YUGIOH',signal:job.signal,onProgress:p=>{
      if(job===control && Number.isFinite(p?.done) && Number.isFinite(p?.total)) progress.value=p.done+' / '+p.total
    }})
    if(job!==control)return
    rows.value=result.rows.map((r,i)=>({...r,key:i,selected:r.candidates?.[0]??null,confirmed:r.confidence==='high'&&!!r.candidates?.length}))
    if(!rows.value.length)throw Error(t('카드 배열을 찾을 수 없습니다. 전체 레시피가 보이는 캡처를 선택하세요.'))
    if(result.suggestedTitle)emit('suggest',result.suggestedTitle.slice(0,100))
  } catch(e){if(!job.signal.aborted){error.value=t(e.message);emit('pending',false)}}
  finally{if(job===control)busy.value=false}
}
function show(row){active.value=active.value===row.key?null:row.key;search.value=false}
function select(row,c){row.selected=c;row.confirmed=true;active.value=null;search.value=false}
async function manual(row,card){
  const job=control
  try{
    const data=await request('/cards/'+card.id+'?lang='+locale.value,{signal:job?.signal})
    if(job!==control||!rows.value.includes(row))return
    const printed=(data.variants??[]).filter(v=>v.image)
    const choices=(printed.length?printed:[{}]).map(v=>({cardId:data.id,variantId:v.id??null,...nameFields(data),number:data.number,image:v.image??card.image,imageUrl:card.imageUrl,rarity:v.rarity,type:data.specs?.type||[data.specs?.k,data.specs?.sub].filter(Boolean).join(' · ')}))
    if(choices.length===1)select(row,choices[0]);else {row.candidates=choices;row.confirmed=false;search.value=false}
  }catch(e){if(!job?.signal.aborted)error.value=e.message}
}
function apply(){
  if(!validRows.value)return
  emit('apply',rows.value.map(r=>({...r.selected,...nameFields(caption(r.selected)),labelLocale:labels.value.has(r.selected.cardId)?locale.value:undefined,section:r.section,quantity:r.quantity})))
  cancel()
}
</script>
<template>
  <section class="capture-panel"><h2>{{ t('뉴런 덱 레시피 가져오기') }}</h2>
    <label>{{ t('전체 레시피 캡처') }}<input ref="input" type="file" accept="image/png,image/jpeg,image/webp" @change="read"></label>
    <p v-if="busy" role="status">{{ t('카드 그림을 대조하는 중…') }} {{ progress }} <button class="text-button" @click="cancel">{{ t('취소') }}</button></p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="labelError" role="alert">{{ labelError }} <button type="button" class="text-button" @click="labelRetry++">{{ t('다시 시도') }}</button></p>
    <template v-if="rows.length"><p aria-live="polite">{{ sections.map(s=>sectionLabel(s)+' '+counts[s]).join(' · ') }} · {{ t('확인 필요') }} {{ pending }}</p>
      <section v-for="s in sections" :key="s"><h3 v-if="counts[s]">{{ sectionLabel(s) }}</h3>
        <div v-for="r in rows.filter(v=>v.section===s)" :key="r.key" class="capture-row">
          <button type="button" class="capture-match" :aria-expanded="active===r.key" @click="show(r)">
            <img :src="r.thumbnail" :alt="t('캡처에서 읽은 카드')">
            <LibraryThumbnail v-if="r.selected" :image="r.selected.image" :src="r.selected.imageUrl"/>
            <span><strong :lang="caption(r.selected)?.language || ''">{{ caption(r.selected)?.name||t('일치하는 카드 찾기') }}</strong><CardTextCredit :card="caption(r.selected)"/><small>{{ r.selected?.number }} · {{ r.confirmed?t('확인됨'):t('확인 필요') }} · ×{{ r.quantity }}</small></span>
          </button>
          <div v-if="active===r.key" class="capture-correct">
            <div class="capture-candidates"><button v-for="(c,i) in r.candidates" :key="[c.cardId,c.variantId,c.artworkIndex].join('-')" type="button" :aria-label="caption(c).name+' '+(i+1)" @click="select(r,c)">
              <LibraryThumbnail :image="c.image" :src="c.imageUrl"/><span :lang="caption(c).language || ''">{{ caption(c).name }}</span><small>{{ c.number }} {{ c.rarity }} {{ c.neuronArtwork ? t('일러스트')+' '+c.neuronArtwork : '' }}</small>
            </button></div>
            <div class="capture-edits"><label>{{ t('구역') }}<select v-model="r.section"><option v-for="k in sections" :key="k" :value="k">{{ sectionLabel(k) }}</option></select></label>
              <label>{{ t('수량') }}<input v-model.number="r.quantity" type="number" min="1" max="999"></label></div>
            <button class="text-button" type="button" @click="search=!search">{{ t('도감에서 직접 찾기') }}</button>
            <button class="text-button" type="button" @click="rows=rows.filter(v=>v!==r);if(!rows.length)cancel()">{{ t('이 항목 제외') }}</button>
            <CatalogPicker v-if="search" game="YUGIOH" @pick="manual(r,$event)"/>
          </div>
        </div>
      </section>
      <div class="lib-actions"><button class="primary" :disabled="!validRows" type="button" @click="apply">{{ t('확인한 카드를 덱에 추가') }}</button><button class="secondary" @click="cancel">{{ t('취소') }}</button></div>
    </template>
  </section>
</template>
<style scoped>
.capture-panel{border-block:1px solid var(--bd);padding-block:1rem;margin-block:1rem}.capture-panel h2{font-size:1.08rem}.capture-panel h3{font-size:1rem}.capture-row{border-bottom:1px solid var(--bd)}.capture-match{display:flex;width:100%;text-align:start;gap:.65rem;align-items:center;border:0;background:transparent;color:var(--tx);padding:.55rem 0}.capture-match>img,.capture-match :deep(.lib-thumbnail){width:2.5rem;max-height:3.6rem;object-fit:contain;flex:0 0 2.5rem}.capture-match span{min-width:0}.capture-match small,.capture-candidates small{display:block;color:var(--mu)}.capture-correct{padding:.5rem 0}.capture-candidates{display:flex;overflow:auto;gap:.45rem}.capture-candidates button{flex:0 0 7rem;padding:.45rem;border:1px solid var(--bd);background:var(--sf);color:var(--tx);border-radius:5px;font-size:.82rem}.capture-candidates :deep(.lib-thumbnail){display:block;width:3.4rem;margin:0 auto .3rem}.capture-edits{display:flex;gap:.7rem;align-items:end}.capture-edits input{width:5rem}.capture-panel input[type=file]{max-width:100%}
</style>
