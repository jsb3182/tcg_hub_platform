<script setup>
import {ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import {pt} from '../pack'
const route=useRoute(),open=ref(-1),dialog=ref(null)
const tabs=[
  {label:'덱 레시피',icon:'M4 5h13v14H4z M8 2h12v14',to:'/decks',pages:['decks','deck-edit','deck-new','shared-deck']},
  {label:'바인더·잡카통',icon:'M3 4h18v16H3z M8 4v16 M8 12h13 M14 4v16',to:'/binder',pages:['binder']},
  {label:'필요·발매',icon:'M3 5h18v16H3z M7 2v6 M17 2v6 M3 10h18',links:[['필요 카드','/decks#deck-needs'],['발매 일정','/releases']],pages:['releases','pack']},
  {label:'금제·소식',icon:'M4 5h16v14H4z M7 9h9 M7 13h6',links:[['새 소식','/news'],['금제 확인','/news#restriction-sources'],['커뮤니티','/community']],pages:['news','community']},
  {label:'수록·지도',icon:'M3 5l6-2 6 3 6-2v15l-6 2-6-3-6 2z M9 3v15 M15 6v15',links:[['카드 도감','/'],['매장 지도','/stores']],pages:['catalog','card','stores']},
]
function show(i){open.value=i;dialog.value.showModal()}
watch(()=>route.fullPath,()=>{dialog.value?.close();open.value=-1})
</script>
<template>
  <nav class="bottom-tabs" :aria-label="pt('빠른 이동')"><template v-for="(tab,i) in tabs" :key="tab.label">
    <component :is="tab.to?'RouterLink':'button'" :to="tab.to||undefined" :type="tab.to?undefined:'button'" :class="{active:tab.pages.includes(route.name)}"
      :aria-haspopup="tab.to?undefined:'dialog'" @click="!tab.to&&show(i)">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path :d="tab.icon"/></svg>
      <span>{{ pt(tab.label) }}</span>
    </component></template></nav>
  <dialog ref="dialog" class="tab-choices" :aria-label="open>=0?pt(tabs[open].label):pt('빠른 이동')" @click="e=>{if(e.target===dialog)dialog.close()}">
    <div v-if="open>=0"><button type="button" class="text-button" @click="dialog.close()">{{ pt('닫기') }}</button>
      <RouterLink v-for="[label,to] in tabs[open].links" :key="to" :to="to" @click="dialog.close()">{{ pt(label) }}</RouterLink></div>
  </dialog>
</template>
<style scoped>
.bottom-tabs{display:none}.tab-choices{width:min(400px,100%);margin:auto auto 0;padding:12px 18px max(14px,env(safe-area-inset-bottom));background:var(--sf);color:var(--tx);border:1px solid var(--bd);border-radius:16px 16px 0 0}
.tab-choices::backdrop{background:rgb(12 18 30/.4)}.tab-choices div{display:grid}.tab-choices button{justify-self:end}.tab-choices a{padding:12px 0;border-top:1px solid var(--bd)}
@media(max-width:760px){.bottom-tabs{display:grid;position:fixed;z-index:12;bottom:0;inset-inline:0;grid-template-columns:repeat(5,minmax(0,1fr));background:var(--sf);border-top:1px solid var(--bd);padding-bottom:env(safe-area-inset-bottom)}.bottom-tabs :is(a,button){display:grid;justify-items:center;align-content:center;gap:2px;min-width:0;min-height:55px;padding:4px 1px;background:transparent;border:0;color:var(--mu);font:inherit;font-size:clamp(9px,2.6vw,12px);line-height:1.15;text-align:center;text-decoration:none}.bottom-tabs .active{color:var(--ac);font-weight:700}:global(body){padding-bottom:calc(58px + env(safe-area-inset-bottom))}}
</style>
