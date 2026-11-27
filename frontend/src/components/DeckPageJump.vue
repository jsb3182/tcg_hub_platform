<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { locale } from '../i18n'

defineProps({ menuOpen: Boolean })
const longPage=ref(false), editing=ref(false), modal=ref(false), atTop=ref(true), atBottom=ref(false)
const words={ko:['페이지 이동','맨 위','맨 아래'],en:['Page navigation','Top','Bottom'],ja:['ページ内移動','先頭','末尾']}
let resize, dialogs, pendingFrame=0

function position(){
  const page=document.scrollingElement
  atTop.value=page.scrollTop<=2
  atBottom.value=page.scrollHeight-page.clientHeight-page.scrollTop<=2
}
function measure(){
  const main=document.querySelector('#content')
  longPage.value=main && main.offsetHeight>window.innerHeight*1.5
  modal.value=!!main?.querySelector('dialog[open]')
  const field=document.activeElement
  editing.value=field?.isContentEditable || field?.matches('textarea,input:not([type]),input[type=text],input[type=number],input[type=search],input[type=url],input[type=email],input[type=password]')
  position()
}
function schedule(){
  if(!pendingFrame)pendingFrame=requestAnimationFrame(()=>{pendingFrame=0;measure()})
}
function jump(end){
  window.scrollTo({top:end?document.scrollingElement.scrollHeight:0,
    behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})
}
onMounted(()=>{
  const main=document.querySelector('#content')
  resize=new ResizeObserver(schedule);resize.observe(main)
  dialogs=new MutationObserver(schedule);dialogs.observe(main,{subtree:true,attributes:true,attributeFilter:['open']})
  window.addEventListener('scroll',position,{passive:true})
  window.addEventListener('resize',schedule)
  document.addEventListener('focusin',schedule)
  document.addEventListener('focusout',schedule)
  measure()
})
onBeforeUnmount(()=>{
  resize?.disconnect();dialogs?.disconnect();cancelAnimationFrame(pendingFrame)
  window.removeEventListener('scroll',position);window.removeEventListener('resize',schedule)
  document.removeEventListener('focusin',schedule);document.removeEventListener('focusout',schedule)
})
</script>
<template>
  <div v-if="longPage&&!menuOpen&&!editing&&!modal" class="deck-jump shell" role="group" :aria-label="words[locale][0]">
    <button v-for="(label,i) in words[locale].slice(1)" :key="i" type="button" :aria-disabled="i?atBottom:atTop" :title="label" @click="jump(i)">
      <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" :class="{down:i}">
        <path d="M4 3h12M5 11l5-5 5 5M10 6v11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg><span>{{ label }}</span>
    </button>
  </div>
</template>
<style scoped>
.deck-jump{display:flex;justify-content:flex-end;gap:.4rem;border-top:1px solid var(--bd)}
.deck-jump button{display:inline-flex;align-items:center;justify-content:center;gap:.35rem;min-width:44px;min-height:44px;padding:0 .55rem;background:var(--bg);border:0;color:var(--tx);font:inherit;font-size:.85rem}
.deck-jump button[aria-disabled=true]{color:var(--mu)}.deck-jump button:hover:not([aria-disabled=true]){color:var(--ac)}
.down{transform:rotate(180deg)}
@media(max-width:760px){
  .deck-jump{position:fixed;inset:auto .5rem calc(66px + env(safe-area-inset-bottom)) auto;width:auto;display:grid;gap:4px;border:0;padding:0;z-index:4}
  .deck-jump button{background:var(--sf);border:1px solid var(--bd);border-radius:50%;box-shadow:0 2px 5px rgb(0 0 0 / .10)}
  .deck-jump span{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}
}
@media(min-width:1250px){
  .deck-jump{position:fixed;top:48%;right:max(.4rem,calc((100vw - 1120px)/2 - 58px));width:auto;display:grid;gap:0;border:1px solid var(--bd);border-radius:7px;background:var(--bg)}
  .deck-jump button{border-radius:6px}.deck-jump button+button{border-top:1px solid var(--bd)}
  .deck-jump span{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}
}
</style>
