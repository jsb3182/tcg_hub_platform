<script setup>
import { computed } from 'vue'
import { sourceLink } from '../api'
import { dateTime, providerName } from '../presentation'
const props = defineProps({ item: { type: Object, required: true }, games: { type: Array, default: () => [] }, review: Boolean })
const game = computed(() => props.games.find(g => g.code === props.item.gameCode)?.name || props.item.gameCode || '공통')
const original = computed(() => sourceLink(props.item.sourceUrl))
</script>
<template>
  <article class="news-item">
    <div class="story-byline">
      <span class="label-tag">{{ game }}</span>
      <span v-if="item.sourceName">{{ item.sourceName }}</span>
      <span v-if="item.provider && !item.sourceName?.includes(providerName(item.provider))">{{ providerName(item.provider) }}</span>
    </div>
    <h3>{{ item.title || '제목 미제공' }}</h3>
    <p v-if="item.summary && item.summary !== item.title" class="story-summary">{{ item.summary }}</p>
    <div class="story-links">
      <time v-if="dateTime(item.publishedAt)" :datetime="item.publishedAt">게시 {{ dateTime(item.publishedAt) }}</time>
      <time v-else-if="dateTime(item.collectedAt)" :datetime="item.collectedAt">수집 {{ dateTime(item.collectedAt) }}</time>
      <a v-if="original" :href="original" target="_blank" rel="noopener noreferrer" :aria-label="(item.title || '소식') + ' 원문 보기'">원문 보기</a>
      <RouterLink v-if="!review && item.gameCode" :to="{name: 'catalog', query: {game: item.gameCode}}">{{ game }} 도감</RouterLink>
    </div>
    <slot></slot>
  </article>
</template>
