<script setup>
import { t as uiText, locale, gameName, supportedLanguage } from '../i18n'

import { computed, defineAsyncComponent, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { mediaPath, request } from '../api'
import {pt, inclusions, shortRarity} from '../pack'
import {traitLabel,traitValueLabel} from '../cardDetailLocale'
import LibraryThumbnail from '../components/LibraryThumbnail.vue'
import ArtworkCredit from '../components/ArtworkCredit.vue'
import CardTextCredit from '../components/CardTextCredit.vue'
import RiftEffectSummary from '../components/RiftEffectSummary.vue'
import CatalogGallery from '../components/CatalogGallery.vue'

const route = useRoute()
const CardDetails = defineAsyncComponent(()=>import('../components/CardDetails.vue'))
const visited = reactive(new Set())
const router = useRouter()
const games = ref([])
const packs = ref([])
const result = ref({ items: [], total: 0 })
const activeGame = computed(() => param('game'))
const gallery = computed(() => param('view') === 'gallery')
const withImage = computed(() => param('withImage') === 'true')
const selectedPack = computed(() => packs.value.find(pack => String(pack.id) === param('packId')))
const filters = reactive(filtersFromRoute())
const filtersOpen = ref(Boolean(param('releaseYear') || param('traitKey')))
const facetOptions=ref({years:[],traitKeys:[],values:[]}), facetBusy=ref(false), facetError=ref(false), facetRetry=ref(0)
const koreanPrintingFilter=key=>activeGame.value==='ONEPIECE' && ['traits','attribute'].includes(key)
const knownTraits=computed(()=>(facetOptions.value.traitKeys || []).filter(key=>traitLabel(activeGame.value,key,locale.value) &&
  (locale.value==='ko' || !koreanPrintingFilter(key) || filters.traitKey===key)))
const traitValues=computed(()=>(facetOptions.value.values || []).map(raw=>({raw:String(raw),
  label:traitValueLabel(activeGame.value,filters.traitKey,raw,locale.value)})).filter(row=>row.label))
const needsPacks = computed(() => filtersOpen.value || Boolean(param('packId')))
const packError = ref('')
const packLoading = ref(false)
const advancedCount = computed(() => ['packId','rarity','inclusion','ygoType','releaseYear','traitValue'].filter(key=>param(key)).length)
const resultsTitle = computed(() => param('q') || advancedCount.value ? uiText("검색 결과") : activeGame.value ? gameName(activeGame.value) : uiText("전체 카드"))
const loading = ref(true)
const error = ref('')
const metaError = ref('')
const reload = ref(0)
const pageSize = 24
const page = computed(() => Math.max(0, Math.min(1000000, Number.parseInt(param('page'), 10) || 0)))
const pageCount = computed(() => Math.ceil(result.value.total / pageSize))
const hasSearchConditions = computed(() => Boolean(param('q') || advancedCount.value || withImage.value || page.value))

function param(key) { return typeof route.query[key] === 'string' ? route.query[key] : '' }
function filtersFromRoute() {
  return { q:param('q'),packId:param('packId'),rarity:param('rarity'),inclusion:param('inclusion'),ygoType:param('ygoType'),
    releaseYear:param('releaseYear'),traitKey:param('traitKey'),traitValue:param('traitValue') }
}
function navigate(changes) {
  const values = { ...route.query, page: '', ...changes }
  const query = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== '' && value != null))
  router.push({ name: 'catalog', query })
}
function apply() {
  navigate({ ...filters,q:filters.q.trim(),rarity:filters.rarity.trim(),traitKey:filters.traitValue?filters.traitKey:'' })
}
function chooseGame(game) {
  const ygo = !game || game==='YUGIOH'
  navigate({ game,packId:'',q:filters.q.trim(),rarity:filters.rarity.trim(),inclusion:ygo?filters.inclusion:'',ygoType:ygo?filters.ygoType:'',
    releaseYear:'',traitKey:'',traitValue:'' })
}
function goPage(index) {
  navigate({page:index ? String(index):''})
  document.getElementById('results-heading')?.focus()
}
function changeView(useGallery) {
  const query = { ...route.query }
  if (useGallery) query.view = 'gallery'
  else delete query.view
  router.replace({ name:'catalog', query })
}
watch(() => JSON.stringify(filtersFromRoute()), () => Object.assign(filters, filtersFromRoute()))
watch([activeGame,filtersOpen,()=>filters.traitKey,facetRetry],async([game,open,key],previous,cleanup)=>{
  const abort=new AbortController();cleanup(()=>abort.abort())
  if(previous?.[0]!==game)facetOptions.value={years:[],traitKeys:[],values:[]}
  facetError.value=false;facetBusy.value=open
  if(!open)return
  const params=new URLSearchParams()
  if(game)params.set('game',game)
  if(game && key)params.set('traitKey',key)
  try{
    const data=await request('/cards/facets?'+params,{signal:abort.signal})
    if(!abort.signal.aborted)facetOptions.value=data
  }catch{if(!abort.signal.aborted)facetError.value=true}
  finally{if(!abort.signal.aborted)facetBusy.value=false}
},{immediate:true})
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
const searchQuery = computed(() => {
  const query = new URLSearchParams({ page:String(page.value), size:String(pageSize), lang:locale.value, order:'edition' })
  for (const key of ['q','game','packId','rarity','inclusion','ygoType','releaseYear','traitKey','traitValue']) {
    if (param(key)) query.set(key,param(key))
  }
  if (withImage.value) query.set('withImage','true')
  return query.toString()
})
watch([searchQuery, reload], async ([query], __, onCleanup) => {
  if (route.name !== 'catalog') return
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  loading.value = true
  visited.clear()
  error.value = ''
  try {
    const data = await request('/cards?' + query, { signal: controller.signal })
    if (!controller.signal.aborted) result.value = data
  }
  catch (cause) { if (!controller.signal.aborted) error.value = cause.message }
  finally { if (!controller.signal.aborted) loading.value = false }
}, { immediate: true })

function reset() {
  router.push({ name: 'catalog', query:gallery.value ? { view:'gallery' } : {} })
}

</script>

<template>
  <header class="catalog-heading">
    <h1>{{ $t("카드 도감") }}</h1>
    <form class="catalog-search" role="search" :aria-label="$t('카드 검색')" @submit.prevent="apply">
      <div class="search-field">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>
        </svg>
        <input v-model="filters.q" type="search" maxlength="120" :aria-label="$t('카드 검색')" :placeholder="$t('카드명·번호·효과')" />
        <button class="search-submit" type="submit">{{ $t("검색") }}</button>
      </div>
      <button type="button" class="filter-toggle secondary" :aria-expanded="filtersOpen" aria-controls="extra-filters" @click="filtersOpen=!filtersOpen">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
          <path d="M3 7h4m4 0h10M3 17h10m4 0h4"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="17" r="2"/>
        </svg>{{ $t("필터") }}<span v-if="advancedCount">{{ advancedCount }}</span>
      </button>
    </form>
  </header>
  <form v-show="filtersOpen" id="extra-filters" class="filter-tray" @submit.prevent="apply">
    <label>{{ $t("수록 팩") }}<select v-model="filters.packId" :disabled="packLoading || !!packError">
      <option value="">{{ packLoading ? $t("팩 불러오는 중…") : $t("모든 팩") }}</option>
      <option v-for="pack in packs" :key="pack.id" :value="String(pack.id)">{{ pack.name }}</option>
    </select></label>
    <label>{{ $t("레어도") }}<input v-model="filters.rarity" maxlength="64" :placeholder="$t('예: UR')" /></label>
    <label>{{ pt('발매 연도') }}<select v-model="filters.releaseYear" :disabled="!facetOptions.years?.length && !filters.releaseYear">
      <option value="">{{ pt('모든 연도') }}</option><option v-for="year in facetOptions.years" :key="year" :value="String(year)">{{ year }}</option>
    </select></label>
    <template v-if="activeGame">
      <label>{{ pt('카드 특성') }}<select v-model="filters.traitKey" :disabled="!knownTraits.length" @change="filters.traitValue=''">
        <option value="">{{ pt('특성 선택') }}</option><option v-for="key in knownTraits" :key="key" :value="key">{{ traitLabel(activeGame,key,locale) }}</option>
      </select></label>
      <label v-if="filters.traitKey">{{ pt('특성 값') }}<select v-model="filters.traitValue" :disabled="facetBusy || facetError || !traitValues.length">
        <option value="">{{ $t('전체') }}</option>
        <option v-if="locale!=='ko' && koreanPrintingFilter(filters.traitKey) && filters.traitValue" :value="filters.traitValue">{{ pt('선택한 한국판 특성') }}</option>
        <option v-for="item in traitValues" :key="item.raw" :value="item.raw">{{ item.label }}</option>
      </select></label>
    </template>
    <template v-if="!activeGame || activeGame==='YUGIOH'">
      <label>{{ pt('수록 구분') }}<select v-model="filters.inclusion"><option value="">{{ $t('전체') }}</option>
        <option v-for="(label,value) in inclusions" :key="value" :value="value">{{ pt(label) }}</option>
      </select></label>
      <label>{{ gameName('YUGIOH') }} · {{ pt('카드 종류') }}<select v-model="filters.ygoType"><option value="">{{ $t('전체') }}</option>
        <option v-for="(label,value) in {MONSTER:'몬스터',SPELL:'마법',TRAP:'함정'}" :key="value" :value="value">{{ pt(label) }}</option>
      </select></label>
    </template>
    <button type="submit" class="secondary">{{ $t("필터 적용") }}</button>
    <p v-if="facetError" class="inline-error" role="alert">{{ pt('필터를 불러오지 못했습니다.') }} <button type="button" class="text-button" @click="facetRetry++">{{ pt('다시 시도') }}</button></p>
  </form>
  <div v-if="metaError || packError" class="inline-error" role="alert">{{ metaError ? $t("게임 목록") : $t("팩 목록") }}{{ $t("을 불러오지 못했습니다.") }}
    <button type="button" class="text-button" @click="reload++">{{ $t("다시 시도") }}</button>
  </div>
  <nav class="game-tabs catalog-games" :aria-label="$t('게임별 보기')">
    <button type="button" :aria-pressed="!activeGame" @click="chooseGame('')">{{ $t("전체") }}</button>
    <button v-for="game in games" :key="game.code" type="button"
      :aria-pressed="activeGame === game.code" @click="chooseGame(game.code)">{{ gameName(game.code) }}</button>
  </nav>
    <section class="catalog-results" aria-labelledby="results-heading" :aria-busy="loading">
      <div v-if="selectedPack" class="pack-banner">
        <img v-if="mediaPath(selectedPack.bannerUrl)" :src="mediaPath(selectedPack.bannerUrl)" alt="" loading="lazy" />
        <div><strong>{{ selectedPack.name }}</strong><small v-if="selectedPack.releaseLabel">{{ selectedPack.releaseLabel }}</small></div>
      </div>
      <div class="section-heading results-heading">
        <h2 id="results-heading" tabindex="-1">{{ resultsTitle }} <span v-if="!loading && !error" class="result-count" role="status">{{ result.total.toLocaleString(locale) }}{{ $t("장") }}</span></h2>
        <button v-if="hasSearchConditions" class="text-button" @click="reset">{{ $t("검색 초기화") }}</button>
        <span v-else-if="!loading && !error && result.items.length" class="result-range">{{ page * pageSize + 1 }}–{{ page * pageSize + result.items.length }} {{ $t("표시") }}</span>
      </div>
      <div class="catalog-display">
        <label class="picture-filter">
          <input type="checkbox" :checked="withImage" @change="navigate({withImage:$event.target.checked ? 'true' : ''})">
          {{ pt('사진 있는 카드') }}
        </label>
        <div class="view-switch" role="group" :aria-label="pt('보기 방식')">
          <button type="button" :aria-pressed="!gallery" @click="changeView(false)">{{ pt('목록') }}</button>
          <button type="button" :aria-pressed="gallery" @click="changeView(true)">{{ pt('배열') }}</button>
        </div>
      </div>
      <p v-if="loading" class="state" role="status">{{ $t("카드를 불러오는 중입니다.") }}</p>
      <div v-else-if="error" class="state" role="alert"><p>{{ error }}</p><button type="button" class="secondary" @click="reload++">{{ $t("다시 시도") }}</button></div>
      <div v-else-if="!result.items.length" class="state">
        <p>{{ hasSearchConditions ? $t("검색 조건에 맞는 카드가 없습니다.") : $t("등록된 카드가 없습니다.") }}</p>
        <button v-if="Object.keys(route.query).length" type="button" class="secondary" @click="reset">{{ $t("전체 카드 보기") }}</button>
      </div>
      <CatalogGallery v-else-if="gallery" :cards="result.items" :query="route.query" />
      <div v-else class="catalog-list">
        <div v-for="card in result.items" :key="card.id" class="catalog-entry"><details class="card-row" @toggle="event=>{if(event.currentTarget.open)visited.add(card.id)}">
          <summary>
            <span class="card-leading">
              <LibraryThumbnail v-slot="{art}" placeholder :image="card.image" :src="card.imageUrl" :language="card.imageLanguage" :printing="card">
                <span class="card-title"><strong :lang="locale">{{ card.language===locale && card.name ? card.name : card.number || $t('이름 미정') }}</strong>
                <small v-if="card.language!==locale || !card.name">{{ pt('이 언어의 카드명 미등록') }}</small>
                <CardTextCredit v-else :card="card"/>
                <small v-if="card.packName">{{ card.packName }}</small>
                <RiftEffectSummary v-if="card.gameCode==='RIFTBOUND'" :card="card"/>
                <small v-if="param('releaseYear') && (card.releaseDate || card.productReleaseDate)">{{ card.releaseDate?$t('발매일'):pt('수록 상품 첫 발매일') }} · <time :datetime="card.releaseDate || card.productReleaseDate">{{ card.releaseDate || card.productReleaseDate }}</time></small>
                <small class="card-id-mobile">{{ [card.language===locale && card.name ? card.number : '',shortRarity(card)].filter(Boolean).join(' · ') }}</small>
                <small v-if="!art?.src && !art?.style" class="catalog-edition">{{ $t('이미지 미등록') }}</small>
                <small v-if="art && (art.language!==locale || art.reference)" class="catalog-edition">
                  <ArtworkCredit :language="art.language" :label-image="!supportedLanguage(art.language)" :printing="art.reference ? card : null" automatic disable-link/>
                </small>
                </span>
              </LibraryThumbnail>
            </span>
            <span class="card-code">{{ card.number }}</span>
            <span class="card-rarity">{{ shortRarity(card) }}</span><span class="chevron" aria-hidden="true"></span>
          </summary>
          <CardDetails v-if="visited.has(card.id)" :card-id="card.id" :catalog-query="route.query" lazy />
        </details>
        <RouterLink class="catalog-open" :to="{name:'card',params:{id:card.id},query:{...route.query,lang:locale}}" :aria-label="pt('카드 상세 보기')+' · '+(card.number||card.name)">{{ pt('상세') }} →</RouterLink></div>
      </div>
      <nav v-if="!loading && !error && (pageCount > 1 || page > 0)" class="pagination" :aria-label="$t('결과 페이지')">
        <button class="secondary" type="button" :disabled="page === 0" @click="goPage(page-1)">{{ $t("이전") }}</button>
        <span>{{ page + 1 }} / {{ Math.max(page + 1, pageCount) }}</span>
        <button class="secondary" type="button" :disabled="page + 1 >= pageCount" @click="goPage(page+1)">{{ $t("다음") }}</button>
      </nav>
    </section>
</template>
<style scoped>
.catalog-entry{position:relative}.catalog-entry+.catalog-entry{border-top:1px solid var(--bd)}.catalog-entry>.card-row>summary{padding-right:5rem}
.catalog-open{position:absolute;inset-inline-end:11px;top:10px;display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:4px;font-size:.82rem;font-weight:600}
.catalog-display,.view-switch,.picture-filter{display:flex;align-items:center}
.catalog-display{justify-content:space-between;gap:12px;margin-block:0 14px}
.picture-filter{gap:8px;min-height:44px;font-size:.875rem;cursor:pointer}
.picture-filter input{width:17px;height:17px;min-height:0;margin:0;accent-color:var(--ac)}
.view-switch{gap:2px;padding:2px;background:var(--bg);border:1px solid var(--bd);border-radius:8px}
.view-switch button{min-height:40px;padding:0 14px;border:0;border-radius:5px;background:transparent;color:var(--mu);font-size:.875rem}
.view-switch button[aria-pressed=true]{background:var(--tx);color:var(--sf);font-weight:650}
.catalog-games{flex-wrap:wrap;overflow:visible}
@media(max-width:600px){
  .catalog-games{gap:4px}
  .catalog-games button{min-height:44px;padding-inline:10px}
}
</style>
