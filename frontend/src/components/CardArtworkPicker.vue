<script setup>
import { computed, ref, watch } from 'vue'
import { locale } from '../i18n'
import { preferredArtwork } from '../artwork'
import { pt } from '../pack'
import ArtworkCredit from './ArtworkCredit.vue'

const props=defineProps({choices:{type:Array,required:true},card:Object,title:String,original:Boolean})
const emit=defineEmits(['failed'])
const selected=ref(null), dialog=ref()
const current=computed(()=>props.choices.find(art=>art.key===selected.value) || preferredArtwork(props.choices,locale.value))
const index=computed(()=>props.choices.indexOf(current.value))
watch([()=>props.card?.id,locale],()=>{selected.value=null;dialog.value?.close()})
</script>
<template>
  <div class="illustration">
    <button v-if="current?.src" type="button" class="localized-card" :aria-label="title+$t(' 이미지 확대')" @click="dialog.showModal()">
      <img :src="current.src" :alt="title" referrerpolicy="no-referrer" @error="emit('failed',current.src)">
    </button>
    <button v-else-if="current?.style" class="atlas" :style="current.style" type="button" :aria-label="title+$t(' 이미지 확대')" @click="dialog.showModal()"></button>
    <span v-else class="atlas missing">{{ original ? $t('이미지 미등록') : pt('이 언어의 이미지 미등록') }}</span>
    <small v-if="current?.src || current?.style" class="edition-note">
      <ArtworkCredit :language="current.language" :automatic="original && selected===null" :printing="current.src ? current.printing || card : null" :label-image="!original && current.language===locale"/>
    </small>
    <div v-if="choices.length>1" class="variant-nav">
      <button type="button" :disabled="index===0" :aria-label="$t('이전 일러스트')" @click="selected=choices[index-1].key">‹</button>
      <span aria-live="polite">{{ index+1 }}/{{ choices.length }}</span>
      <button type="button" :disabled="index+1>=choices.length" :aria-label="$t('다음 일러스트')" @click="selected=choices[index+1].key">›</button>
    </div>
    <dialog ref="dialog" class="zoom" :aria-label="$t('카드 이미지 확대')" @click="e=>{if(e.target===dialog)dialog.close()}">
      <img v-if="current?.src" class="localized-large" :src="current.src" :alt="title" referrerpolicy="no-referrer">
      <div v-else-if="current?.style" class="atlas large" :style="current.style" role="img" :aria-label="title"></div>
      <button class="secondary" type="button" @click="dialog.close()">{{ $t('닫기') }}</button>
    </dialog>
  </div>
</template>
<style scoped>
.localized-card{display:block;width:100%;padding:0;border:0;background:transparent;cursor:zoom-in}.localized-card img{display:block;width:100%;height:auto;border-radius:6px}
.localized-large{display:block;margin:auto;max-width:100%;max-height:76vh;object-fit:contain}
.edition-note{display:block;margin:.4rem 0 0;color:var(--mu);font-size:.75rem;line-height:1.4}
.missing{padding:8px;text-align:center;word-break:keep-all;overflow-wrap:anywhere}.variant-nav{display:flex;align-items:center;gap:3px;font-variant-numeric:tabular-nums}
.variant-nav button{min-height:40px;min-width:30px}.variant-nav span{white-space:nowrap}
</style>
