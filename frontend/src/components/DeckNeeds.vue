<script setup>
import {ref,watch} from 'vue'
import {locale,t} from '../i18n'
import {useSession} from '../stores/session'
import CardTextCredit from './CardTextCredit.vue'
const props=defineProps({deckId:[String,Number],revision:Number})
const open=ref(false),items=ref([]),more=ref(null),busy=ref(false),error=ref(''),reload=ref(0)
const session=useSession()
let generation=0,controller
async function load(after){
  const current=generation
  busy.value=true;error.value=''
  try{
    const params=new URLSearchParams({deckId:String(props.deckId||0),after:String(after||0),lang:locale.value})
    const page=await session.authenticatedRequest('/me/decks/needed?'+params,{signal:controller.signal})
    if(current===generation){items.value.push(...page.items);more.value=page.next}
  }catch(cause){if(current===generation&&!controller.signal.aborted)error.value=cause.message}
  finally{if(current===generation)busy.value=false}
}
watch([open,()=>props.deckId,()=>props.revision,()=>session.account?.email,locale,reload],(_,__,cleanup)=>{
  generation++;controller=new AbortController()
  const active=controller;cleanup(()=>active.abort())
  items.value=[];more.value=null;busy.value=false;error.value=''
  if(open.value&&session.account)load(0)
})
</script>
<template><details class="lib-panel" @toggle="open=$event.target.open"><summary>{{ t('필요 카드') }}</summary>
  <p>{{ t(deckId?'저장한 덱과 바인더의 인쇄본별 수량을 비교합니다.':'저장한 덱을 모두 구성하는 데 필요한 수량을 바인더와 비교합니다.') }}</p>
  <p v-if="error" role="alert">{{ error }} <button type="button" class="text-button" @click="reload++">{{ t('다시 시도') }}</button></p>
  <p v-if="busy" role="status">{{ t('불러오는 중') }}</p>
  <ul v-if="items.length" class="lib-list"><li v-for="card in items" :key="card.cardId"><div>
    <RouterLink :to="{name:'card',params:{id:card.cardId},query:{lang:locale}}" :lang="card.language || ''">{{ card.name }}</RouterLink>
    <CardTextCredit :card="card"/>
    <small>{{ card.number }} · {{ t('보유 수량') }} {{ card.owned }} / {{ card.required }}</small></div>
    <strong>{{ t('부족') }} {{ card.required-card.owned }}</strong></li></ul>
  <p v-else-if="!busy&&!error">{{ t('부족한 인쇄본이 없습니다.') }}</p>
  <button v-if="more" type="button" :disabled="busy" class="secondary" @click="load(more)">{{ t('더 보기') }}</button>
</details></template>
