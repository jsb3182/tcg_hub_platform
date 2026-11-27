<script setup>
import { t as uiText,gameName,locale } from '../i18n'

import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api'
import DeckRecipe from '../components/DeckRecipe.vue'
import '../styles/library.css'
const route=useRoute(), deck=ref(null), error=ref(''), retry=ref(0)
watch([()=>route.params.token,retry,locale],async ([token],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  deck.value=null;error.value=''
  try {
    const item=await request('/shared/decks/'+encodeURIComponent(token)+'?lang='+locale.value,{signal:abort.signal})
    if(!abort.signal.aborted) deck.value=item
  } catch(cause) {if(!abort.signal.aborted)error.value=cause.status===404?uiText("공유가 종료됐거나 존재하지 않는 덱입니다."):cause.message}
},{immediate:true})
</script>
<template>
  <header class="lib-heading"><h1>{{ $t("공유 덱") }}</h1><RouterLink to="/decks">{{ $t("내 덱") }}</RouterLink></header>
  <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
  <DeckRecipe v-else-if="deck" :deck="deck" :game-name="gameName(deck.gameCode)" /><p v-else role="status">{{ $t("덱을 불러오는 중입니다.") }}</p>
</template>
