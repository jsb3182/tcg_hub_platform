<script setup>
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {languages,locale} from '../i18n'
import {sourceLink} from '../api'
import {namuArticleUrl} from '../wikiReferences'
import {pt} from '../pack'
import {useSession} from '../stores/session'
import {useTranslationDrafts} from '../stores/translationDrafts'

const props=defineProps({cardId:{type:Number,required:true},disabled:Boolean})
const emit=defineEmits(['busy'])
const session=useSession(),{drafts}=useTranslationDrafts()
const open=ref(false),lang=ref(locale.value),rows=ref([]),ready=ref(false),loading=ref(false),saving=ref(false)
const error=ref(''),notice=ref(''),retry=ref(0)
const endpoint=computed(()=>'/catalog/cards/'+props.cardId+'/translations')
const key=computed(()=>props.cardId+'/'+lang.value)
const blank={name:'',effect:'',sourceUrl:'',basis:'TRANSLATED_NAME',version:0}
const record=computed(()=>rows.value.find(r=>r.lang===lang.value)||blank)
const form=computed(()=>drafts.get(key.value)||record.value)
const articleUrl=computed(()=>namuArticleUrl(form.value.sourceUrl.trim()))
const dirty=computed(()=>drafts.has(key.value))
const conflict=computed(()=>ready.value && dirty.value && record.value.version!==form.value.version)
const emptyText=computed(()=>!form.value.name.trim() && !form.value.effect.trim())
const removal=computed(()=>emptyText.value && !!(record.value.name || record.value.effect))
let active=true
onBeforeUnmount(()=>{active=false})
function normalize(row){return {lang:row.lang,name:row.name||'',effect:row.effect||'',sourceUrl:row.sourceUrl||'',basis:row.basis||'TRANSLATED_NAME',version:row.version}}
watch([open,endpoint,retry],async([shown,path],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  ready.value=false;error.value='';loading.value=shown
  if(!shown)return
  try{
    const result=await session.adminRequest(path,{signal:abort.signal})
    if(!abort.signal.aborted){rows.value=result.map(normalize);ready.value=true}
  }catch(e){if(!abort.signal.aborted)error.value=e.message}
  finally{if(!abort.signal.aborted)loading.value=false}
},{immediate:true})
watch(lang,()=>{notice.value='';if(ready.value)error.value=''})
function edit(field,value){
  const next={...form.value,[field]:value}
  if(['name','effect','sourceUrl','basis'].every(k=>next[k]===record.value[k]))drafts.delete(key.value)
  else drafts.set(key.value,next)
  notice.value='';error.value=''
}
function discard(){drafts.delete(key.value);error.value='';notice.value=''}
async function save(){
  if(!ready.value || saving.value || props.disabled || !dirty.value || (emptyText.value&&!removal.value))return
  const original=form.value
  const name=original.name.trim(),effect=original.effect.trim(),sourceUrl=original.sourceUrl.trim()
  if((name || effect) && !sourceLink(sourceUrl)){error.value=pt('확인한 원문 URL을 입력하세요.');return}
  if((name || effect) && articleUrl.value && original.basis==='PRINTED_NAME'){error.value=pt('인쇄본 원문에는 이 게임의 공식 사이트 URL을 입력하세요.');return}
  error.value='';notice.value='';saving.value=true;emit('busy',true)
  try{
    const result=await session.adminRequest(endpoint.value+'/'+lang.value,{method:'PUT',body:{
      name,effect,sourceUrl:name || effect?sourceUrl:'',basis:original.basis,version:record.value.version,
    }})
    if(!active)return
    rows.value=[...rows.value.filter(row=>row.lang!==lang.value),normalize(result)]
    drafts.delete(key.value);notice.value=pt(name || effect?'언어 보완을 저장했습니다.':'언어 보완을 지웠습니다.')
  }catch(e){
    if(active){
      if(e.status===409){notice.value=pt('다른 변경이 있습니다. 서버 값과 입력한 내용을 비교하세요.');retry.value++}
      else error.value=e.message
    }
  }finally{if(active){saving.value=false;emit('busy',false)}}
}
</script>
<template>
  <details class="ops-card card-translations" @toggle="open=$event.currentTarget.open">
    <summary>{{ pt('카드명·효과 언어 보완') }}</summary>
    <form @submit.prevent="save">
      <label>{{ pt('보완할 언어') }}<select v-model="lang" :disabled="saving"><option v-for="(label,code) in languages" :value="code" :key="code">{{ label }}{{ drafts.has(cardId+'/'+code)?' *':'' }}</option></select></label>
      <p v-if="loading" role="status">{{ pt('불러오는 중') }}</p>
      <fieldset v-if="ready || dirty" :disabled="disabled || saving || !ready">
        <label>{{ pt('카드명') }}<input :value="form.name" :lang="lang" maxlength="320" @input="edit('name',$event.target.value)"></label>
        <label>{{ pt('카드 효과') }}<textarea :value="form.effect" :lang="lang" maxlength="8000" rows="3" @input="edit('effect',$event.target.value)"></textarea></label>
        <label>{{ pt('표기 근거') }}<select :value="form.basis" @change="edit('basis',$event.target.value)">
          <option value="TRANSLATED_NAME">{{ pt('확인한 번역') }}</option><option value="PRINTED_NAME">{{ pt('같은 인쇄본 원문') }}</option>
        </select></label>
        <label>{{ pt('확인한 원문 URL') }}<input type="url" :value="form.sourceUrl" maxlength="2048" inputmode="url" placeholder="https://…" :required="!!(form.name.trim() || form.effect.trim())" @input="edit('sourceUrl',$event.target.value)"></label>
        <small v-if="form.basis==='PRINTED_NAME'" class="muted">{{ pt('인쇄본 원문에는 이 게임의 공식 사이트 URL을 입력하세요.') }}</small>
        <a v-if="articleUrl" :href="articleUrl" target="_blank" rel="noopener noreferrer">{{ pt('나무위키 문서 열기') }}</a>
        <div v-if="conflict" class="translation-conflict">
          <strong>{{ pt('현재 서버 값') }}</strong>
          <p v-if="record.name" :lang="lang">{{ record.name }}</p><p v-if="record.effect" :lang="lang">{{ record.effect }}</p>
          <p v-if="!record.name && !record.effect">{{ pt('등록된 보완이 없습니다.') }}</p>
          <small v-else>{{ pt(record.basis==='PRINTED_NAME'?'같은 인쇄본 원문':'확인한 번역') }}</small>
          <a v-if="sourceLink(record.sourceUrl)" :href="sourceLink(record.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ record.sourceUrl }}</a>
        </div>
        <p v-if="removal" class="muted">{{ pt('저장하면 이 언어의 보완 내용을 지웁니다.') }}</p>
        <div class="catalog-savebar"><button type="submit" class="primary" :disabled="!dirty || saving || (emptyText && !removal)">{{ pt(removal?'이 언어 보완 지우기':conflict?'입력한 값으로 다시 저장':'언어 보완 저장') }}</button>
          <button v-if="dirty" type="button" class="text-button" @click="discard">{{ pt(conflict?'서버 값 사용':'입력 취소') }}</button></div>
      </fieldset>
      <p v-if="error" role="alert" class="inline-error">{{ error }} <button v-if="!ready" type="button" class="text-button" @click="retry++">{{ pt('다시 시도') }}</button></p>
      <p v-if="notice" role="status">{{ notice }}</p>
    </form>
  </details>
</template>
<style scoped>
.card-translations summary{min-height:44px;align-content:center;font-weight:650;cursor:pointer}
.card-translations form{display:grid;gap:.75rem}.card-translations fieldset{min-width:0;display:grid;gap:.65rem;margin:0;padding:0;border:0}
.card-translations label{display:grid;gap:.25rem}.card-translations :is(textarea,input,select){width:100%;min-width:0}
.translation-conflict{border-inline-start:3px solid var(--ac);padding-inline-start:.7rem;overflow-wrap:anywhere}.translation-conflict p{white-space:pre-line;margin:.35rem 0}.translation-conflict a{display:block}
</style>
