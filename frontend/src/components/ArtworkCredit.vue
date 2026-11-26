<script setup>
import { computed } from 'vue'
import { sourceLink } from '../api'
import { editionName, locale, supportedLanguage, t } from '../i18n'

const props = defineProps({ language: String, printing: Object, automatic: Boolean, labelImage:Boolean })
const prefix = computed(() => {
  if (props.automatic && supportedLanguage(props.language) && props.language !== locale.value) return t('대체 이미지')
  return props.labelImage ? t('카드 이미지') : ''
})
const credit = computed(() => {
  const card = props.printing
  if (!card) return ''
  if (!card.imageProduct) return t('수록 제품 미확인')
  const different = card.productCode && card.productCode !== 'PROMO' && card.productCode !== card.imageProduct
  return t(different ? '다른 제품의 그림' : '그림 수록 제품') + ' · ' + card.imageProduct
})
const link = computed(() => sourceLink(props.printing?.imageSource))
</script>

<template>
  <template v-if="prefix"><span class="edition-term">{{ prefix }} ·</span>{{ ' ' }}</template><span class="edition-term">{{ editionName(language) }}</span>
  <template v-if="credit"> · <a v-if="link" :href="link" target="_blank" rel="noopener noreferrer">{{ credit }}</a><span v-else>{{ credit }}</span></template>
</template>

<style scoped>
.edition-term { display: inline-block; max-width: 100%; word-break: keep-all; }
</style>
