<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import NewsItem from '../components/NewsItem.vue'

const route = useRoute()
const router = useRouter()
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
function navigate(game, index) {
  const query = {}
  if (game) query.game = game
  if (index) query.page = String(index)
  router.push({ name: 'news', query })
}
watch(retry, async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  gameError.value = ''
  try { games.value = await request('/games', {signal: controller.signal}) }
  catch (cause) { if (!controller.signal.aborted) gameError.value = cause.message }
}, {immediate: true})
watch([selected, page, retry], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  busy.value = true
  error.value = ''
  const query = new URLSearchParams({page: page.value, size: pageSize})
  if (selected.value) query.set('game', selected.value)
  try {
    const result = await request('/news?' + query, {signal: controller.signal})
    items.value = result.items
    total.value = result.total
  } catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
  finally { if (!controller.signal.aborted) busy.value = false }
}, {immediate: true})
</script>

<template>
  <header class="page-heading"><h1>새 소식</h1></header>
  <nav class="game-tabs" aria-label="소식 게임별 보기">
    <button type="button" :aria-pressed="!selected" @click="navigate('', 0)">전체</button>
    <button v-for="game in games" :key="game.code" type="button" :aria-pressed="selected === game.code" @click="navigate(game.code, 0)">{{ game.name }}</button>
  </nav>
  <p v-if="gameError" role="alert" class="inline-error">게임 목록을 불러오지 못했습니다. <button class="text-button" @click="retry++">다시 시도</button></p>
  <section class="news-results" :aria-busy="busy" aria-label="공개 소식">
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
</template>
