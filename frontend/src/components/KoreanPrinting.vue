<script setup>
import { computed } from 'vue'
import { locale } from '../i18n'
import { sourceLink } from '../api'

defineProps({ printing: { type: Object, required: true } })
const labels = {
  ko: ['같은 카드의 한국 수록 번호', '확인된 가장 이른 국내 상품 발매일', '한국 공식 카드 정보'],
  en: ['Korean printing of this card', 'Earliest documented Korean product release', 'Official Korean card details'],
  ja: ['このカードの韓国版収録番号', '確認できた韓国収録商品の最古の発売日', '韓国公式カード情報'],
}
const text = computed(() => labels[locale.value] || labels.ko)
</script>

<template>
  <div>
    <small>{{ text[0] }}</small>
    <p><a :href="sourceLink(printing.printingSourceUrl)" target="_blank" rel="noopener noreferrer">{{ printing.number }}</a></p>
    <a :href="sourceLink(printing.cardUrl)" target="_blank" rel="noopener noreferrer">{{ text[2] }}</a>
  </div>
  <div v-if="printing.productReleasedOn">
    <small>{{ text[1] }}</small>
    <p><a :href="sourceLink(printing.productSourceUrl)" target="_blank" rel="noopener noreferrer">
      <time :datetime="printing.productReleasedOn">{{ printing.productReleasedOn }}</time>
    </a></p>
  </div>
</template>
