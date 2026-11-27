<script setup>
import { computed } from 'vue'
import { locale } from '../i18n'
import { sourceLink } from '../api'
import { pt } from '../pack'

const props=defineProps({card:Object, effect:Boolean, link:Boolean, detailed:Boolean})
const field=computed(()=>props.effect?'effect':'name')
const language=computed(()=>props.effect?props.card?.effectLanguage:props.card?.language)
const basis=computed(()=>props.card?.[field.value+'Basis'])
const basisLabels={
  RELATED_PRINTING:'다른 인쇄의 참고 카드명', IMPORTED_LABEL:'기존 도감 표기',
  IMPORTED_ORIGINAL:'기존 도감 원문', PRINTED_NAME:'인쇄본 표기', SOURCE_LABEL:'수집처 표기',
  TRANSLATED_NAME:'번역 카드명',REVIEWED_TRANSLATION:'검수한 번역 효과',REVIEWED_PRINTING:'확인한 인쇄본 효과',
}
const source=computed(()=>props.link ? sourceLink(props.card?.[field.value+'ReferenceUrl']) : '')
const languageLabel=computed(()=>{
  if(!language.value || language.value===locale.value)return ''
  return pt(({ko:'한국어',en:'영어',ja:'일본어'})[language.value] || '언어 미확인')
})
const basisLabel=computed(()=>{
  if(!basis.value || (!props.detailed && basis.value==='PRINTED_NAME'))return ''
  return pt(props.effect && basis.value==='RELATED_PRINTING'?'다른 인쇄의 참고 효과':basisLabels[basis.value] || '')
})
</script>
<template>
  <small v-if="languageLabel || basisLabel || source" class="card-text-credit">
    <span v-if="languageLabel">{{ pt(effect?'효과 언어':'카드명 언어') }} · {{ languageLabel }}</span>
    <template v-if="basisLabel"><span v-if="languageLabel" aria-hidden="true"> · </span><span>{{ basisLabel }}</span></template>
    <template v-if="source"><span v-if="languageLabel || basisLabel" aria-hidden="true"> · </span><a :href="source" rel="noopener noreferrer" target="_blank">{{ pt(effect?'효과 출처':basis==='RELATED_PRINTING'?'참고 인쇄본':'카드명 출처') }}</a></template>
  </small>
</template>
<style scoped>.card-text-credit{display:block;color:var(--mu);font-size:.78rem;line-height:1.4;overflow-wrap:anywhere}.card-text-credit span{word-break:keep-all}</style>
