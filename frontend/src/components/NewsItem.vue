<script setup>
import { t as uiText, locale, gameName } from '../i18n'

import { computed } from 'vue'
import { sourceLink } from '../api'
import { dateTime, providerName } from '../presentation'
const props = defineProps({ item: { type: Object, required: true }, games: { type: Array, default: () => [] }, review: Boolean })
const game = computed(() => props.item.gameCode ? gameName(props.item.gameCode) : uiText("공통"))
const original = computed(() => sourceLink(props.item.sourceUrl))
const contentLanguage = computed(() => props.item.contentLanguage || props.item.originalLanguage || '')
const summaryLanguage = computed(() => props.item.summaryLanguage === undefined ? contentLanguage.value : props.item.summaryLanguage || '')
const showSummary = computed(() => props.item.summary && props.item.summary !== props.item.title)
const languageNames = { ko:'한국어', en:'영어', ja:'일본어' }
function annotated(code, meaning) {
  return [uiText(meaning), uiText(languageNames[code])].filter(Boolean).join(' · ')
}
const translationNote = computed(() => {
  const status=props.item.translationStatus
  if (status==='PENDING') return annotated(contentLanguage.value,'번역 준비 중 · 원문 표시')
  if (status==='ORIGINAL') return annotated(contentLanguage.value,'원문')
  if (status!=='TRANSLATED') return ''
  return showSummary.value && summaryLanguage.value!==contentLanguage.value
    ? annotated(contentLanguage.value,'제목 번역')+' / '+annotated(summaryLanguage.value,'원문 요약')
    : annotated(contentLanguage.value,'번역문')
})
</script>
<template>
  <article class="news-item">
    <div class="story-byline">
      <span class="label-tag">{{ game }}</span>
      <span v-if="item.sourceName">{{ item.sourceName }}</span>
      <span v-if="item.provider && !item.sourceName?.includes(providerName(item.provider)) && !(item.provider==='OFFICIAL_NEWS' && item.sourceName?.includes($t('공지')))">{{ providerName(item.provider) }}</span>
    </div>
    <h3 :lang="item.title ? contentLanguage : locale">{{ item.title || $t("제목 미제공") }}</h3>
    <p v-if="showSummary" class="story-summary" :lang="summaryLanguage">{{ item.summary }}</p>
    <details v-if="item.translationStatus==='TRANSLATED' && item.originalTitle && (item.originalTitle!==item.title || (item.originalSummary && item.originalSummary!==item.summary))" class="story-original"><summary>{{ $t('원문') }}</summary><strong :lang="item.originalLanguage || ''">{{ item.originalTitle }}</strong><p v-if="item.originalSummary" :lang="item.originalLanguage || ''">{{ item.originalSummary }}</p></details>
    <div class="story-links">
      <span v-if="translationNote">{{ translationNote }}</span>
      <time v-if="dateTime(item.publishedAt)" :datetime="item.publishedAt">{{ $t("게시") }} {{ dateTime(item.publishedAt) }}</time>
      <time v-else-if="dateTime(item.collectedAt)" :datetime="item.collectedAt">{{ $t("수집") }} {{ dateTime(item.collectedAt) }}</time>
      <a v-if="original" :href="original" target="_blank" rel="noopener noreferrer" :aria-label="(item.title || $t('소식')) + $t(' 원문 보기')">{{ $t("원문 보기") }}</a>
      <RouterLink v-if="!review && item.gameCode" :to="{name: 'catalog', query: {game: item.gameCode}}">{{ game }} {{ $t("도감") }}</RouterLink>
    </div>
    <slot></slot>
  </article>
</template>
