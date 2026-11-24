<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { mediaPath, request } from '../api'
import CardDetails from '../components/CardDetails.vue'

const route = useRoute()
const router = useRouter()
const games = ref([])
const packs = ref([])
const result = ref({ items: [], total: 0 })
const activeGame = computed(() => param('game'))
const selectedPack = computed(() => packs.value.find(pack => String(pack.id) === param('packId')))
const gamePacks = computed(() => packs.value.filter(pack => !activeGame.value || pack.gameCode === activeGame.value))
const filters = reactive({ q: '', packId: '', rarity: '' })
const loading = ref(true)
const error = ref('')
const metaError = ref('')
const reload = ref(0)
const pageSize = 24
const page = computed(() => Math.max(0, Math.min(1000000, Number.parseInt(param('page'), 10) || 0)))
const pageCount = computed(() => Math.ceil(result.value.total / pageSize))
const hasSearchConditions = computed(() => Boolean(param('q') || param('packId') || param('rarity') || page.value))

function param(key) { return typeof route.query[key] === 'string' ? route.query[key] : '' }
function filtersFromRoute() {
  return { q: param('q'), packId: param('packId'), rarity: param('rarity') }
}
function navigate(changes) {
  const values = { ...route.query, page: '', ...changes }
  const query = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== '' && value != null))
  router.push({ name: 'catalog', query })
}
function apply() {
  navigate({ q: filters.q.trim(), packId: filters.packId, rarity: filters.rarity.trim() })
}
function chooseGame(game) {
  navigate({ game, packId: '', q: filters.q.trim(), rarity: filters.rarity.trim() })
}
watch(() => route.query, () => Object.assign(filters, filtersFromRoute()), { immediate: true })
watch(reload, async (_, __, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const options = { signal: controller.signal }
  metaError.value = ''
  try {
    const [g, p] = await Promise.all([request('/games', options), request('/packs', options)])
    games.value = g
    packs.value = p
  } catch (cause) { if (!controller.signal.aborted) metaError.value = cause.message }
}, { immediate: true })
watch([() => route.fullPath, reload], async (_, __, onCleanup) => {
  if (route.name !== 'catalog') return
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const query = new URLSearchParams({ page: String(page.value), size: String(pageSize) })
  for (const key of ['q', 'game', 'packId', 'rarity']) if (param(key)) query.set(key, param(key))
  loading.value = true
  error.value = ''
  try { result.value = await request('/cards?' + query, { signal: controller.signal }) }
  catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
  finally { if (!controller.signal.aborted) loading.value = false }
}, { immediate: true })

function reset() {
  Object.assign(filters, { q: '', packId: '', rarity: '' })
  router.push({ name: 'catalog' })
}
function gameName(code) { return games.value.find(g => g.code === code)?.name || code }
</script>

<template>
  <header class="page-heading"><h1>카드 도감</h1></header>
  <nav class="game-tabs" aria-label="게임별 보기">
    <button type="button" :aria-pressed="!activeGame" @click="chooseGame('')">전체</button>
    <button v-for="game in games" :key="game.code" type="button"
      :aria-pressed="activeGame === game.code" @click="chooseGame(game.code)">{{ game.name }}</button>
  </nav>
  <div class="catalog-layout">
    <aside class="filters">
      <form @submit.prevent="apply">
        <div class="section-heading"><h2>검색 조건</h2><button type="button" class="text-button" @click="reset">초기화</button></div>
        <label>카드 검색<input v-model="filters.q" type="search" maxlength="100" placeholder="카드명 · 번호 · 효과" /></label>
        <div class="filter-pair">
          <label>수록 팩<select v-model="filters.packId"><option value="">모든 팩</option>
            <option v-for="pack in gamePacks" :key="pack.id" :value="String(pack.id)">{{ pack.name }}</option>
          </select></label>
          <label>레어도<input v-model="filters.rarity" maxlength="40" placeholder="예: UR" /></label>
        </div>
        <button type="submit" class="primary wide">검색</button>
        <div v-if="metaError" class="inline-error" role="alert">게임·팩 목록을 불러오지 못했습니다.
          <button type="button" class="text-button" @click="reload++">다시 시도</button>
        </div>
      </form>
    </aside>
    <section class="catalog-results" aria-labelledby="results-heading" :aria-busy="loading">
      <div v-if="selectedPack" class="pack-banner">
        <img v-if="mediaPath(selectedPack.bannerUrl)" :src="mediaPath(selectedPack.bannerUrl)" alt="" loading="lazy" />
        <div><strong>{{ selectedPack.name }}</strong><small v-if="selectedPack.releaseLabel">{{ selectedPack.releaseLabel }}</small></div>
      </div>
      <div class="section-heading results-heading">
        <h2 id="results-heading">{{ activeGame ? gameName(activeGame) : '전체 카드' }}</h2>
        <span v-if="!loading && !error" role="status">{{ result.total.toLocaleString('ko-KR') }}장</span>
      </div>
      <p v-if="loading" class="state" role="status">카드를 불러오는 중입니다.</p>
      <div v-else-if="error" class="state" role="alert"><p>{{ error }}</p><button type="button" class="secondary" @click="reload++">다시 시도</button></div>
      <div v-else-if="!result.items.length" class="state">
        <p>{{ hasSearchConditions ? '검색 조건에 맞는 카드가 없습니다.' : '등록된 카드가 없습니다.' }}</p>
        <button v-if="Object.keys(route.query).length" type="button" class="secondary" @click="reset">전체 카드 보기</button>
      </div>
      <template v-else>
        <details v-for="card in result.items" :key="card.id" class="card-row">
          <summary>
            <span class="card-code">{{ card.number || gameName(card.gameCode) }}</span>
            <span class="card-title"><strong>{{ card.name || card.originalName || '이름 미정' }}</strong><small>{{ card.packName }}</small></span>
            <span v-if="card.rarity" class="rarity">{{ card.rarity }}</span><span class="chevron" aria-hidden="true"></span>
          </summary>
          <CardDetails :card-id="card.id" lazy />
        </details>
      </template>
      <nav v-if="!loading && !error && (pageCount > 1 || page > 0)" class="pagination" aria-label="결과 페이지">
        <button class="secondary" type="button" :disabled="page === 0" @click="navigate({page: page > 1 ? String(page - 1) : ''})">이전</button>
        <span>{{ page + 1 }} / {{ Math.max(page + 1, pageCount) }}</span>
        <button class="secondary" type="button" :disabled="page + 1 >= pageCount" @click="navigate({page: String(page + 1)})">다음</button>
      </nav>
    </section>
  </div>
</template>
