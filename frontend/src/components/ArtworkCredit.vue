<script setup>
import { computed } from 'vue'
import { sourceLink } from '../api'
import { editionName, locale, supportedLanguage, t } from '../i18n'
import {pt} from '../pack'

const props = defineProps({ language: String, printing: Object, automatic: Boolean, labelImage:Boolean, disableLink:Boolean })
const prefix = computed(() => {
  if (props.automatic && supportedLanguage(props.language) && props.language !== locale.value) return t('대체 이미지')
  return props.labelImage ? t('카드 이미지') : ''
})
const credit = computed(() => {
  const card = props.printing
  if (!card) return ''
  if(card.imageBasis==='CARD_REFERENCE') return pt('카드 참고 이미지')
  if(card.imageBasis==='SELECTED_ARTWORK') return pt('선택한 일러스트')
  if(card.gameCode!=='ONEPIECE' && !card.productCode && !card.imageProduct) return ''
  if (!card.imageProduct) return t('수록 제품 미확인')
  const different = card.productCode && card.productCode !== 'PROMO' && card.productCode !== card.imageProduct
  return t(different ? '다른 제품의 그림' : '그림 수록 제품') + ' · ' + card.imageProduct
})
const link = computed(() => props.disableLink?'':sourceLink(props.printing?.imageSource))
const imageLanguage=computed(()=>props.printing?.imageBasis==='CARD_REFERENCE'
  ? pt(({ko:'한국어',en:'영어',ja:'일본어'})[props.language] || '언어 미확인') : editionName(props.language))
</script>

<template>
  <template v-if="prefix"><span class="edition-term">{{ prefix }} ·</span>{{ ' ' }}</template><span class="edition-term">{{ imageLanguage }}</span>
  <template v-if="credit"> · <a v-if="link" :href="link" target="_blank" rel="noopener noreferrer">{{ credit }}</a><span v-else>{{ credit }}</span></template>
</template>

<style scoped>
.edition-term { display: inline-block; max-width: 100%; word-break: keep-all; }
</style>
