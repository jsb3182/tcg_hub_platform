<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api'
import DeckRecipe from '../components/DeckRecipe.vue'
import '../styles/library.css'
const route=useRoute(), deck=ref(null), gameName=ref(''), error=ref(''), retry=ref(0)
watch([()=>route.params.token,retry],async ([token],_,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  deck.value=null;error.value=''
  try {
    const [item,games]=await Promise.all([request('/shared/decks/'+encodeURIComponent(token),{signal:abort.signal}),request('/games',{signal:abort.signal})])
    if(!abort.signal.aborted) { deck.value=item; gameName.value=games.find(g=>g.code===item.gameCode)?.name }
  } catch(cause) {if(!abort.signal.aborted)error.value=cause.status===404?'공유가 종료됐거나 존재하지 않는 덱입니다.':cause.message}
},{immediate:true})
</script>
<template>
  <header class="lib-heading"><h1>공유 덱</h1><RouterLink to="/decks">내 덱</RouterLink></header>
  <p v-if="error" role="alert">{{ error }} <button class="text-button" @click="retry++">다시 시도</button></p>
  <DeckRecipe v-else-if="deck" :deck="deck" :game-name="gameName" /><p v-else role="status">덱을 불러오는 중입니다.</p>
</template>
