<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { mediaPath, request } from '../api'
import CardDetails from '../components/CardDetails.vue'
import LibraryThumbnail from '../components/LibraryThumbnail.vue'

const route = useRoute()
const router = useRouter()
const games = ref([])
const packs = ref([])
const result = ref({ items: [], total: 0 })
const activeGame = computed(() => param('game'))
const selectedPack = computed(() => packs.value.find(pack => String(pack.id) === param('packId')))
const filters = reactive({ q: '', packId: '', rarity: '' })
const filtersOpen = ref(false)
const needsPacks = computed(() => filtersOpen.value || Boolean(param('packId')))
const packError = ref('')
const packLoading = ref(false)
const advancedCount = computed(() => Number(Boolean(param('packId'))) + Number(Boolean(param('rarity'))))
const resultsTitle = computed(() => param('q') || advancedCount.value ? '검색 결과' : activeGame.value ? gameName(activeGame.value) : '전체 카드')
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
function goPage(index) {
  navigate({page:index ? String(index):''})
  document.getElementById('results-heading')?.focus()
}
watch(() => route.query, () => Object.assign(filters, filtersFromRoute()), { immediate: true })
watch(reload, async (_, __, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const options = { signal: controller.signal }
  metaError.value = ''
  try {
    games.value = await request('/games', options)
  } catch (cause) { if (!controller.signal.aborted) metaError.value = cause.message }
}, { immediate: true })
watch([activeGame, needsPacks, reload], async ([game, needed], _, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  packs.value = []; packError.value = ''; packLoading.value = false
  if (!needed) return
  packLoading.value = true
  try {
    const rows = await request('/packs?' + new URLSearchParams({game}), {signal:controller.signal})
    if (!controller.signal.aborted) packs.value = rows
  } catch (cause) { if (!controller.signal.aborted) packError.value = cause.message }
  finally { if (!controller.signal.aborted) packLoading.value = false }
}, {immediate:true})
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
  <header class="catalog-heading">
    <h1>카드 도감</h1>
    <form class="catalog-search" role="search" aria-label="카드 검색" @submit.prevent="apply">
      <div class="search-field">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>
        </svg>
        <input v-model="filters.q" type="search" maxlength="120" aria-label="카드 검색" placeholder="카드명·번호·효과" />
        <button class="search-submit" type="submit">검색</button>
      </div>
      <button type="button" class="filter-toggle secondary" :aria-expanded="filtersOpen" aria-controls="extra-filters" @click="filtersOpen=!filtersOpen">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
          <path d="M3 7h4m4 0h10M3 17h10m4 0h4"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="17" r="2"/>
        </svg>필터<span v-if="advancedCount">{{ advancedCount }}</span>
      </button>
    </form>
  </header>
  <form v-show="filtersOpen" id="extra-filters" class="filter-tray" @submit.prevent="apply">
    <label>수록 팩<select v-model="filters.packId" :disabled="packLoading || !!packError">
      <option value="">{{ packLoading ? '팩 불러오는 중…' : '모든 팩' }}</option>
      <option v-for="pack in packs" :key="pack.id" :value="String(pack.id)">{{ pack.name }}</option>
    </select></label>
    <label>레어도<input v-model="filters.rarity" maxlength="64" placeholder="예: UR" /></label>
    <button type="submit" class="secondary">필터 적용</button>
  </form>
  <div v-if="metaError || packError" class="inline-error" role="alert">{{ metaError ? '게임 목록' : '팩 목록' }}을 불러오지 못했습니다.
    <button type="button" class="text-button" @click="reload++">다시 시도</button>
  </div>
  <nav class="game-tabs catalog-games" aria-label="게임별 보기">
    <button type="button" :aria-pressed="!activeGame" @click="chooseGame('')">전체</button>
    <button v-for="game in games" :key="game.code" type="button"
      :aria-pressed="activeGame === game.code" @click="chooseGame(game.code)">{{ game.name }}</button>
  </nav>
    <section class="catalog-results" aria-labelledby="results-heading" :aria-busy="loading">
      <div v-if="selectedPack" class="pack-banner">
        <img v-if="mediaPath(selectedPack.bannerUrl)" :src="mediaPath(selectedPack.bannerUrl)" alt="" loading="lazy" />
        <div><strong>{{ selectedPack.name }}</strong><small v-if="selectedPack.releaseLabel">{{ selectedPack.releaseLabel }}</small></div>
      </div>
      <div class="section-heading results-heading">
        <h2 id="results-heading" tabindex="-1">{{ resultsTitle }} <span v-if="!loading && !error" class="result-count" role="status">{{ result.total.toLocaleString('ko-KR') }}장</span></h2>
        <button v-if="hasSearchConditions" class="text-button" @click="reset">검색 초기화</button>
        <span v-else-if="!loading && !error && result.items.length" class="result-range">{{ page * pageSize + 1 }}–{{ page * pageSize + result.items.length }} 표시</span>
      </div>
      <p v-if="loading" class="state" role="status">카드를 불러오는 중입니다.</p>
      <div v-else-if="error" class="state" role="alert"><p>{{ error }}</p><button type="button" class="secondary" @click="reload++">다시 시도</button></div>
      <div v-else-if="!result.items.length" class="state">
        <p>{{ hasSearchConditions ? '검색 조건에 맞는 카드가 없습니다.' : '등록된 카드가 없습니다.' }}</p>
        <button v-if="Object.keys(route.query).length" type="button" class="secondary" @click="reset">전체 카드 보기</button>
      </div>
      <div v-else class="catalog-list">
        <details v-for="card in result.items" :key="card.id" class="card-row">
          <summary>
            <span class="card-leading">
              <LibraryThumbnail v-if="card.image" :image="card.image" />
              <span class="card-title"><strong>{{ card.name || card.originalName || '이름 미정' }}</strong>
                <small v-if="card.packName">{{ card.packName }}</small>
                <small class="card-id-mobile">{{ [card.number,card.rarity].filter(Boolean).join(' · ') }}</small>
              </span>
            </span>
            <span class="card-code">{{ card.number }}</span>
            <span class="card-rarity">{{ card.rarity }}</span><span class="chevron" aria-hidden="true"></span>
          </summary>
          <CardDetails :card-id="card.id" lazy />
        </details>
      </div>
      <nav v-if="!loading && !error && (pageCount > 1 || page > 0)" class="pagination" aria-label="결과 페이지">
        <button class="secondary" type="button" :disabled="page === 0" @click="goPage(page-1)">이전</button>
        <span>{{ page + 1 }} / {{ Math.max(page + 1, pageCount) }}</span>
        <button class="secondary" type="button" :disabled="page + 1 >= pageCount" @click="goPage(page+1)">다음</button>
      </nav>
    </section>
</template>
