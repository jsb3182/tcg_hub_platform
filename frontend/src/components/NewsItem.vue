<script setup>
import { computed } from 'vue'
import { sourceLink } from '../api'
import { dateTime, providerName } from '../presentation'
const props = defineProps({ item: { type: Object, required: true }, games: { type: Array, default: () => [] }, review: Boolean })
const game = computed(() => props.games.find(g => g.code === props.item.gameCode)?.name || props.item.gameCode || '공통')
const original = computed(() => sourceLink(props.item.sourceUrl))
const contentLanguage = computed(() => props.item.contentLanguage || props.item.originalLanguage || '')
const summaryLanguage = computed(() => props.item.summaryLanguage === undefined ? contentLanguage.value : props.item.summaryLanguage || '')
const showSummary = computed(() => props.item.summary && props.item.summary !== props.item.title)
const languageNames = { ko: '한국어', en: '영어', ja: '일본어' }
const translationNote = computed(() => {
  const language = languageNames[contentLanguage.value]
  const originalText = language ? `${language} 원문` : '원문'
  switch (props.item.translationStatus) {
    case 'PENDING': return `번역 준비 중 · ${originalText} 표시`
    case 'TRANSLATED': {
      if (showSummary.value && summaryLanguage.value !== contentLanguage.value) {
        const source = languageNames[summaryLanguage.value]
        return [language ? `${language} 제목 번역` : '제목 번역', source ? `${source} 원문 요약` : '원문 요약'].join(' · ')
      }
      return language ? `${language} 번역` : '번역문'
    }
    case 'ORIGINAL': return originalText
    default: return ''
  }
})
</script>
<template>
  <article class="news-item">
    <div class="story-byline">
      <span class="label-tag">{{ game }}</span>
      <span v-if="item.sourceName">{{ item.sourceName }}</span>
      <span v-if="item.provider && !item.sourceName?.includes(providerName(item.provider))">{{ providerName(item.provider) }}</span>
    </div>
    <h3 :lang="item.title ? contentLanguage : 'ko'">{{ item.title || '제목 미제공' }}</h3>
    <p v-if="showSummary" class="story-summary" :lang="summaryLanguage">{{ item.summary }}</p>
    <div class="story-links">
      <span v-if="translationNote">{{ translationNote }}</span>
      <time v-if="dateTime(item.publishedAt)" :datetime="item.publishedAt">게시 {{ dateTime(item.publishedAt) }}</time>
      <time v-else-if="dateTime(item.collectedAt)" :datetime="item.collectedAt">수집 {{ dateTime(item.collectedAt) }}</time>
      <a v-if="original" :href="original" target="_blank" rel="noopener noreferrer" :aria-label="(item.title || '소식') + ' 원문 보기'">원문 보기</a>
      <RouterLink v-if="!review && item.gameCode" :to="{name: 'catalog', query: {game: item.gameCode}}">{{ game }} 도감</RouterLink>
    </div>
    <slot></slot>
  </article>
</template>
