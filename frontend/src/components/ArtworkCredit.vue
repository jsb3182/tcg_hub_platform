<script setup>
import { computed } from 'vue'
import { sourceLink } from '../api'
import { editionName, t } from '../i18n'

const props = defineProps({ language: String, printing: Object })
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
  <span>{{ editionName(language) }}</span>
  <template v-if="credit"> · <a v-if="link" :href="link" target="_blank" rel="noopener noreferrer">{{ credit }}</a><span v-else>{{ credit }}</span></template>
</template>
