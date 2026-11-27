<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import { locale, supportedLanguage, gameName } from '../i18n'
import NewsItem from '../components/NewsItem.vue'
import {pt} from '../pack'

const route = useRoute()
const router = useRouter()
const language = computed(() => supportedLanguage(route.query.lang) ? route.query.lang : locale.value)
const games = ref([])
const items = ref([])
const total = ref(0)
const busy = ref(true)
const gameError = ref('')
const error = ref('')
const retry = ref(0)
const selected = computed(() => typeof route.query.game === 'string' ? route.query.game : '')
const page = computed(() => Math.max(0, Math.min(1000000, parseInt(route.query.page, 10) || 0)))
const pageSize = 20
const pages = computed(() => Math.ceil(total.value / pageSize))
function navigate(game, index, lang = language.value) {
  const query = { lang }
  if (game) query.game = game
  if (index) query.page = String(index)
  router.push({ name: 'news', query })
}
watch(() => route.fullPath, () => {
  if (route.name === 'news' && !supportedLanguage(route.query.lang)) {
    router.replace({ name: 'news', query: { ...route.query, lang: locale.value }, hash: route.hash })
  }
}, { immediate: true })
watch(retry, async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  gameError.value = ''
  try { games.value = await request('/games', {signal: controller.signal}) }
  catch (cause) { if (!controller.signal.aborted) gameError.value = cause.message }
}, {immediate: true})
watch([selected, page, language, retry], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  busy.value = true
  error.value = ''
  const query = new URLSearchParams({page: page.value, size: pageSize, lang: language.value})
  if (selected.value) query.set('game', selected.value)
  try {
    const result = await request('/news?' + query, {signal: controller.signal})
    if (controller.signal.aborted) return
    items.value = result.items
    total.value = result.total
  } catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
  finally { if (!controller.signal.aborted) busy.value = false }
}, {immediate: true})
</script>

<template>
  <div class="news-page">
  <header class="page-heading news-heading">
    <h1>{{ $t("새 소식") }}</h1>

  </header>
  <details id="restriction-sources" :open="route.hash==='#restriction-sources'"><summary>{{ pt('금제 확인') }}</summary>
    <p><a href="https://www.yugioh.co.kr/site/limit_regulation.php" target="_blank" rel="noopener noreferrer">{{ $t('한국 OCG 금지·제한 목록') }}</a></p>
    <RouterLink :to="{name:'deck-new',query:{game:'YUGIOH',lang:locale}}">{{ pt('내 덱의 대회 제한 확인') }}</RouterLink>
  </details>
  <nav class="game-tabs" :aria-label="$t('소식 게임별 보기')">
    <button type="button" :aria-pressed="!selected" @click="navigate('', 0)">{{ $t("전체") }}</button>
    <button v-for="game in games" :key="game.code" type="button" :aria-pressed="selected === game.code" @click="navigate(game.code, 0)">{{ gameName(game.code,game.name) }}</button>
  </nav>
  <p v-if="selected === 'YUGIOH'" class="story-links">
    <a href="https://www.yugioh.co.kr/board/board_list.php?b_category=notice" target="_blank" rel="noopener noreferrer">{{ $t("한국 공식 공지") }}</a>
    <a href="https://www.yugioh-card.com/asia/news/" target="_blank" rel="noopener noreferrer">{{ $t("아시아 OCG 공식 공지") }}</a>
  </p>
  <p v-if="gameError" role="alert" class="inline-error">{{ $t("게임 목록을 불러오지 못했습니다.") }} <button class="text-button" @click="retry++">{{ $t("다시 시도") }}</button></p>
  <section class="news-results" :aria-busy="busy" :aria-label="$t('공개 소식')">
    <div v-if="!busy && !error" class="section-heading results-heading">
      <h2>{{ $t("공개 소식") }} <span class="result-count" role="status">{{ total.toLocaleString(locale) }}{{ $t("건") }}</span></h2>
    </div>
    <p v-if="busy" role="status" class="state">{{ $t("소식을 불러오는 중입니다.") }}</p>
    <div v-else-if="error" role="alert" class="state"><p>{{ error }}</p><button class="secondary" @click="retry++">{{ $t("다시 시도") }}</button></div>
    <div v-else-if="!items.length" class="state"><p>{{ $t("공개된 소식이 없습니다.") }}</p>
      <button v-if="page > 0" class="secondary" @click="navigate(selected, 0)">{{ $t("첫 페이지") }}</button>
    </div>
    <div v-else class="news-list"><NewsItem v-for="item in items" :key="item.id" :item="item" :games="games" /></div>
    <nav v-if="!busy && !error && (pages > 1 || page > 0)" class="pagination" :aria-label="$t('소식 페이지')">
      <button class="secondary" :disabled="page === 0" @click="navigate(selected, page - 1)">{{ $t("이전") }}</button>
      <span>{{ page + 1 }} / {{ Math.max(page + 1, pages) }}</span>
      <button class="secondary" :disabled="page + 1 >= pages" @click="navigate(selected, page + 1)">{{ $t("다음") }}</button>
    </nav>
  </section>
  </div>
</template>
