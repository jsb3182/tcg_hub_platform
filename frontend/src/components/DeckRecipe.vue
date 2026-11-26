<script setup>
import { t as uiText } from '../i18n'

import { computed, ref } from 'vue'
import { sectionLabel, stateLabel } from '../library'
import LibraryThumbnail from './LibraryThumbnail.vue'
const props = defineProps({ deck:{type:Object,required:true}, gameName:String })
const imageArea=ref(null), busy=ref(false), error=ref('')
const groups=computed(()=>props.deck.rule.sections.map(s=>({key:s.section,entries:props.deck.entries.filter(e=>e.section===s.section)})))
async function download() {
  busy.value=true; error.value=''
  try {
    await document.fonts.ready
    const {toBlob}=await import('html-to-image')
    const background=getComputedStyle(imageArea.value).backgroundColor
    const blob=await toBlob(imageArea.value,{pixelRatio:1.5,backgroundColor:background,skipFonts:true})
    if(!blob) throw new Error()
    const url=URL.createObjectURL(blob)
    const link=document.createElement('a')
    link.href=url; link.download=(props.deck.name.replace(/[<>:"/\\|?*]/g,'_').slice(0,80)||uiText("덱"))+'.png'
    document.body.appendChild(link); link.click(); link.remove()
    setTimeout(()=>URL.revokeObjectURL(url),60000)
  } catch { error.value=uiText("이미지를 저장하지 못했습니다. 다시 시도해 주세요.") }
  finally { busy.value=false }
}
</script>
<template>
  <section class="lib-panel"><div class="lib-heading"><h2>{{ $t("덱 레시피") }}</h2><button class="secondary" :disabled="busy" @click="download">{{ busy?$t("이미지 만드는 중…"):$t("PNG 저장") }}</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <article ref="imageArea" class="lib-recipe">
      <h3>{{ deck.name }}</h3><small>{{ gameName || deck.gameCode }} · {{ stateLabel(deck.state) }} · {{ deck.entries.reduce((sum,e)=>sum+e.quantity,0) }}{{ $t("장") }}</small>
      <section v-for="group in groups" :key="group.key"><h4>{{ sectionLabel(group.key) }} · {{ group.entries.reduce((sum,e)=>sum+e.quantity,0) }}{{ $t("장") }}</h4>
        <ul v-if="group.entries.length"><li v-for="e in group.entries" :key="e.cardId"><div class="lib-print"><LibraryThumbnail :image="e.image" :src="e.image ? undefined : e.imageUrl" /><span>{{ e.name }} <small>{{ e.number }}</small></span></div><b>×{{ e.quantity }}</b></li></ul>
        <small v-else>{{ $t("등록된 카드가 없습니다.") }}</small>
      </section>
    </article>
  </section>
</template>
