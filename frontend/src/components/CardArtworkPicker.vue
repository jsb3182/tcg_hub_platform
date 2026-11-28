<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { locale } from '../i18n'
import { preferredArtwork } from '../artwork'
import { pt } from '../pack'
import ArtworkCredit from './ArtworkCredit.vue'

const props=defineProps({choices:{type:Array,required:true},card:Object,title:String,original:Boolean,hasAlternatives:Boolean,failed:Boolean})
const emit=defineEmits(['failed','alternatives','retry'])
const selected=ref(null), dialog=ref(), picture=ref(), alternativeButton=ref(), enlarged=ref(false)
const current=computed(()=>props.choices.find(art=>art.key===selected.value) || preferredArtwork(props.choices,locale.value))
const index=computed(()=>props.choices.indexOf(current.value))
const otherLabel=computed(()=>(props.original
  ? {ko:'다른 판본 닫기',en:'Hide other artwork',ja:'別のカード画像を閉じる'}
  : {ko:'다른 판본 사진 보기',en:'View other artwork',ja:'別のカード画像を見る'})[locale.value])
async function show(){
  enlarged.value=true
  await nextTick()
  if(dialog.value && !dialog.value.open)dialog.value.showModal()
}
function move(step){
  const next=props.choices[index.value+step]
  if(next)selected.value=next.key
}
function focusPicture(){(picture.value || alternativeButton.value)?.focus({preventScroll:true})}
defineExpose({focusPicture})
watch([()=>props.card?.id,()=>props.original,locale],()=>{selected.value=null;dialog.value?.close()})
watch(current,art=>{if(!art && dialog.value?.open)dialog.value.close()})
</script>
<template>
  <div class="illustration">
    <button v-if="current?.src" ref="picture" type="button" class="localized-card" :aria-label="title+$t(' 이미지 확대')" @click="show">
      <img :src="current.src" :alt="title" referrerpolicy="no-referrer" @error="emit('failed',current.src)">
    </button>
    <button v-else-if="current?.style" ref="picture" class="atlas" :style="current.style" type="button" :aria-label="title+$t(' 이미지 확대')" @click="show"></button>
    <span v-else class="atlas missing" :class="{compact:!hasAlternatives}">
      {{ failed ? pt('사진을 불러오지 못했습니다.') : hasAlternatives ? pt('이 언어의 이미지 미등록') : $t('이미지 미등록') }}
    </span>
    <button v-if="failed" class="other-art" type="button" data-png-skip @click="emit('retry')">{{ pt('다시 시도') }}</button>
    <small v-if="current?.src || current?.style" class="edition-note">
      <ArtworkCredit :language="current.language" :automatic="original && selected===null" :printing="current.src ? current.printing || card : null" :label-image="!original && current.language===locale"/>
    </small>
    <div v-if="choices.length>1" class="variant-nav">
      <button type="button" :disabled="index===0" :aria-label="$t('이전 일러스트')" @click="move(-1)">‹</button>
      <span aria-live="polite">{{ index+1 }}/{{ choices.length }}</span>
      <button type="button" :disabled="index+1>=choices.length" :aria-label="$t('다음 일러스트')" @click="move(1)">›</button>
    </div>
    <button v-if="hasAlternatives" ref="alternativeButton" class="other-art" type="button" :aria-expanded="original" data-png-skip @click="emit('alternatives')">{{ otherLabel }}</button>
    <dialog ref="dialog" class="zoom" :aria-label="$t('카드 이미지 확대')" @close="enlarged=false"
      @keydown.left.prevent="move(-1)" @keydown.right.prevent="move(1)" @click="e=>{if(e.target===dialog)dialog.close()}">
      <template v-if="enlarged">
        <img v-if="current?.src" class="localized-large" :src="current.src" :alt="title" referrerpolicy="no-referrer" @error="emit('failed',current.src)">
        <div v-else-if="current?.style" class="atlas large" :style="current.style" role="img" :aria-label="title"></div>
        <div class="zoom-tools">
          <small v-if="current" class="zoom-credit">
            <ArtworkCredit :language="current.language" :printing="current.src ? current.printing || card : null"/>
          </small>
          <div v-if="choices.length>1" class="zoom-pages">
            <button type="button" class="secondary" :aria-label="$t('이전 일러스트')" :disabled="index===0" @click="move(-1)">‹</button>
            <span aria-live="polite">{{ index+1 }}/{{ choices.length }}</span>
            <button type="button" class="secondary" :aria-label="$t('다음 일러스트')" :disabled="index+1>=choices.length" @click="move(1)">›</button>
          </div>
          <button class="secondary" type="button" @click="dialog.close()">{{ $t('닫기') }}</button>
        </div>
      </template>
    </dialog>
  </div>
</template>
<style scoped>
.localized-card{display:block;width:100%;padding:0;border:0;background:transparent;cursor:zoom-in}.localized-card img{display:block;margin-inline:auto;max-width:100%;width:100%;height:auto;max-height:250px;object-fit:contain;border-radius:6px}
.localized-large{display:block;margin:auto;max-width:100%;max-height:calc(100vh - 150px);object-fit:contain}
.edition-note{display:block;margin:.4rem 0 0;color:var(--mu);font-size:.75rem;line-height:1.4}
.missing{padding:8px;text-align:center;word-break:keep-all;overflow-wrap:anywhere}.variant-nav{display:flex;align-items:center;gap:3px;font-variant-numeric:tabular-nums}
.variant-nav button{min-height:40px;min-width:30px}.variant-nav span{white-space:nowrap}
.missing.compact{display:block;width:auto;aspect-ratio:auto;padding:0;background:transparent;border:0;text-align:start}
.other-art{display:block;min-height:44px;padding:4px 0;border:0;background:transparent;color:var(--ac);text-align:start;text-decoration:underline;text-underline-offset:.15em;font-size:.8rem}
.zoom-tools,.zoom-pages{display:flex;align-items:center;justify-content:center;gap:8px}.zoom-tools{flex-wrap:wrap;width:max-content;max-width:100%;margin:10px auto 0;padding:4px 8px;border-radius:8px;background:var(--sf);color:var(--tx)}.zoom-credit{max-width:25ch;overflow-wrap:anywhere}
.zoom-tools .secondary{min-width:44px;min-height:44px}.zoom-pages span{min-width:3ch;font-size:.85rem;font-variant-numeric:tabular-nums}
.illustration :is(button.atlas,.localized-card){scroll-margin-block:80px}
@media(max-width:500px){.localized-card img{max-height:174px}}
</style>
