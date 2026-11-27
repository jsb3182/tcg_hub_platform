<script setup>
import {computed} from 'vue'
import {gameName,t} from '../i18n'
import {sectionLabel,deckName} from '../library'
const props=defineProps({deck:{type:Object,required:true},image:String,ordinal:Number})
const summary=computed(()=>{
  const d=props.deck,counts=d.sectionCounts?{...d.sectionCounts}:(Array.isArray(d.entries)?d.entries.reduce((out,e)=>{out[e.section]=(out[e.section]||0)+(Number(e.quantity)||0);return out},{}):{})
  if(d.gameCode==='YUGIOH')for(const [key,k] of [['MAIN','mainCount'],['EXTRA','extraCount'],['SIDE','sideCount']])if(counts[key]==null && d[k]!=null)counts[key]=d[k]
  const rows=Object.entries(counts).map(([key,n])=>[sectionLabel(key),n])
  if(d.gameCode==='WEISS' && d.cxCount!=null)rows.push(['CX',d.cxCount])
  if(!rows.length && Number.isFinite(d.cards))rows.push([t('카드'),d.cards])
  return rows
})
</script>
<template>
<div class="deck-banner">
  <img v-if="image" class="banner-art" :src="image" alt="">
  <span v-if="ordinal" class="banner-index" aria-hidden="true">{{ ordinal }}</span>
  <div class="banner-names"><small>{{ gameName(deck.gameCode) }}</small>
    <span v-if="deck.nameJa" lang="ja">{{ deck.nameJa }}</span>
    <strong :lang="deck.name?'ko':undefined">{{ deck.name||deckName(deck) }}</strong>
    <span v-if="deck.nameEn" lang="en">{{ deck.nameEn }}</span>
  </div>
  <dl v-if="summary.length"><div v-for="[part,n] in summary" :key="part"><dt>{{ part }}</dt><dd>{{ n }}</dd></div></dl>
</div>
</template>
<style scoped>
.deck-banner{position:relative;isolation:isolate;overflow:hidden;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:18px clamp(12px,3vw,26px);min-height:116px;border:1px solid var(--bd);border-radius:14px;background:var(--sf);color:var(--tx)}
.banner-art{position:absolute;z-index:-2;inset-block:0;inset-inline-end:0;width:min(62%,470px);height:100%;object-fit:cover;object-position:center 36%;opacity:.33;mask-image:linear-gradient(to right,transparent,#000 45%,transparent);-webkit-mask-image:linear-gradient(to right,transparent,#000 45%,transparent)}
.banner-index{position:absolute;z-index:-1;inset-inline-start:.12em;bottom:-.28em;color:var(--bd);font-size:clamp(90px,16vw,132px);font-weight:780;line-height:1}
.banner-names{display:grid;gap:1px;min-width:0;overflow-wrap:anywhere}.banner-names strong{font-size:clamp(1rem,2.5vw,1.45rem);line-height:1.25}.banner-names :is(span,small){color:var(--mu);font-size:.77rem;line-height:1.35}
.deck-banner dl{margin:0;font-variant-numeric:tabular-nums}.deck-banner dl div{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:baseline}.deck-banner dt{font-size:.73rem;color:var(--mu)}.deck-banner dd{font-weight:700;margin:0;text-align:right}
</style>
