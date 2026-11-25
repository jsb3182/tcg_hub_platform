<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import NewsItem from '../components/NewsItem.vue'

const route = useRoute()
const router = useRouter()
const languages = { ko: '한국어', en: 'English', ja: '日本語' }
const preferenceKey = 'tcg.news.language'
function supportedLanguage(value) {
  return typeof value === 'string' && Object.hasOwn(languages, value)
}
function savedLanguage() {
  try {
    const value = localStorage.getItem(preferenceKey)
    if (supportedLanguage(value)) return value
  } catch { /* Storage can be unavailable in private browsing. */ }
  return 'ko'
}
const preference = ref(savedLanguage())
const language = computed(() => supportedLanguage(route.query.lang) ? route.query.lang : preference.value)
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
function selectLanguage(value) {
  if (!supportedLanguage(value)) return
  preference.value = value
  try { localStorage.setItem(preferenceKey, value) } catch { /* The URL retains this choice. */ }
  navigate(selected.value, page.value, value)
}
watch(() => route.fullPath, () => {
  if (route.name === 'news' && !supportedLanguage(route.query.lang)) {
    router.replace({ name: 'news', query: { ...route.query, lang: preference.value }, hash: route.hash })
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
    <h1>새 소식</h1>
    <label class="news-language">게시글 언어
      <select :value="language" @change="selectLanguage($event.target.value)">
        <option v-for="(name, code) in languages" :key="code" :value="code" :lang="code">{{ name }}</option>
      </select>
    </label>
  </header>
  <nav class="game-tabs" aria-label="소식 게임별 보기">
    <button type="button" :aria-pressed="!selected" @click="navigate('', 0)">전체</button>
    <button v-for="game in games" :key="game.code" type="button" :aria-pressed="selected === game.code" @click="navigate(game.code, 0)">{{ game.name }}</button>
  </nav>
  <p v-if="selected === 'YUGIOH'" class="story-links">
    <a href="https://www.yugioh.co.kr/board/board_list.php?b_category=notice" target="_blank" rel="noopener noreferrer">한국 공식 공지</a>
    <a href="https://www.yugioh-card.com/asia/news/" target="_blank" rel="noopener noreferrer">아시아 OCG 공식 공지</a>
  </p>
  <p v-if="gameError" role="alert" class="inline-error">게임 목록을 불러오지 못했습니다. <button class="text-button" @click="retry++">다시 시도</button></p>
  <section class="news-results" :aria-busy="busy" aria-label="공개 소식">
    <div v-if="!busy && !error" class="section-heading results-heading">
      <h2>공개 소식 <span class="result-count" role="status">{{ total.toLocaleString('ko-KR') }}건</span></h2>
    </div>
    <p v-if="busy" role="status" class="state">소식을 불러오는 중입니다.</p>
    <div v-else-if="error" role="alert" class="state"><p>{{ error }}</p><button class="secondary" @click="retry++">다시 시도</button></div>
    <div v-else-if="!items.length" class="state"><p>공개된 소식이 없습니다.</p>
      <button v-if="page > 0" class="secondary" @click="navigate(selected, 0)">첫 페이지</button>
    </div>
    <div v-else class="news-list"><NewsItem v-for="item in items" :key="item.id" :item="item" :games="games" /></div>
    <nav v-if="!busy && !error && (pages > 1 || page > 0)" class="pagination" aria-label="소식 페이지">
      <button class="secondary" :disabled="page === 0" @click="navigate(selected, page - 1)">이전</button>
      <span>{{ page + 1 }} / {{ Math.max(page + 1, pages) }}</span>
      <button class="secondary" :disabled="page + 1 >= pages" @click="navigate(selected, page + 1)">다음</button>
    </nav>
  </section>
  </div>
</template>
