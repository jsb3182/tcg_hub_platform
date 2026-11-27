<script setup>
import { t as uiText } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request } from '../api'
import { useSession } from '../stores/session'
import { bytes, dateTime, providerName } from '../presentation'
import NewsItem from '../components/NewsItem.vue'
import AdminAccess from '../components/AdminAccess.vue'
import AdminTools from '../components/AdminTools.vue'
import AdminXSource from '../components/AdminXSource.vue'
import { locale, gameName } from '../i18n'
import AdminCatalog from '../components/AdminCatalog.vue'
import AdminReleases from '../components/AdminReleases.vue'
import AdminProviders from '../components/AdminProviders.vue'
import AdminCommunityReports from '../components/AdminCommunityReports.vue'
import {pt} from '../pack'

const session = useSession()
const tab = ref('overview')
const tabs = {overview:'서버 상태',sources:'수집 출처',review:'검수 대기',catalog:'도감 편집',releases:'발매 일정 관리',posts:'게시물 관리',stores:'매장 관리',users:'회원 권한',server:'서버 제어'}
const intervals=ref({})
const catalogPanel=ref(null)
const releasesPanel=ref(null)
const catalogBusy=ref(false)
function selectTab(next) {
  if (tab.value === 'catalog' && next !== 'catalog' && catalogPanel.value && !catalogPanel.value.mayLeave()) return
  if (tab.value === 'releases' && next !== 'releases' && !releasesPanel.value?.mayLeave()) return
  tab.value=next
}
const states = computed(()=>({IDLE: uiText("대기"), RUNNING: uiText("수집 중"), OK: uiText("수집 성공"), ERROR: uiText("수집 오류"), BLOCKED: uiText("수집 차단"), QUEUED: uiText("실행 예약"), PAUSED: uiText("일시정지")}))
const snapshot = ref(null)
const games = ref([])
const snapshotBusy = ref(false)
const snapshotError = ref('')
const checkedAt = ref('')
const reviewItems = ref([])
const reviewGames = ref({})
const reviewPage = ref(0)
const reviewTotal = ref(0)
const reviewSize = 12
const reviewBusy = ref(false)
const reviewError = ref('')
const activeAction = ref('')
const notice = ref('')
const actionError = ref('')
const reviewPages = computed(() => Math.ceil(reviewTotal.value / reviewSize))
const sources = computed(() => snapshot.value?.sources || [])

const gameCounts = computed(() => Object.entries(snapshot.value?.cardCounts || {}))
const diskUsed = computed(() => {
  const { diskTotalBytes: total, diskUsableBytes: free } = snapshot.value || {}
  return Number.isFinite(total) && Number.isFinite(free) && total >= free ? total - free : null
})
let snapshotController
let reviewController
let gamesController
let timer
let mounted = false

async function loadSnapshot() {
  if (!session.isAdmin || session.adminAccessBlocked) return
  snapshotController?.abort()
  const controller = snapshotController = new AbortController()
  snapshotBusy.value = true
  snapshotError.value = ''
  try {
    const data = await session.adminRequest('/operations', {signal: controller.signal})
    if (!controller.signal.aborted) {
      snapshot.value = data
      checkedAt.value = new Date().toISOString()
    }
  } catch (cause) { if (!controller.signal.aborted) snapshotError.value = cause.message }
  finally { if (!controller.signal.aborted) snapshotBusy.value = false }
}
async function loadReview() {
  if (!session.isAdmin || session.adminAccessBlocked) return
  reviewController?.abort()
  const controller = reviewController = new AbortController()
  reviewBusy.value = true
  reviewError.value = ''
  try {
    const query = new URLSearchParams({page: reviewPage.value, size: reviewSize,lang:locale.value})
    const data = await session.adminRequest('/review?' + query, {signal: controller.signal})
    if (controller.signal.aborted) return
    if (!data.items.length && reviewPage.value > 0) {
      reviewPage.value = Math.max(0, Math.ceil(data.total / reviewSize) - 1)
      return
    }
    reviewItems.value = data.items
    reviewTotal.value = data.total
  } catch (cause) { if (!controller.signal.aborted) reviewError.value = cause.message }
  finally { if (!controller.signal.aborted) reviewBusy.value = false }
}
function refresh() {
  if (tab.value === 'review') loadReview()
  else loadSnapshot()
}
function onSubscriptionSaved(username) {
  notice.value='@'+username+' · '+uiText('구독을 추가했습니다.')
  loadSnapshot()
}
function refreshWhenVisible() {
  if (document.visibilityState === 'visible' && session.isAdmin && ['overview','sources'].includes(tab.value) &&
      !activeAction.value && !snapshotBusy.value) loadSnapshot()
}
async function act(path, body, message) {
  if (!session.isAdmin || session.adminAccessBlocked || activeAction.value) return
  activeAction.value = path
  notice.value = ''
  actionError.value = ''
  try {
    await session.adminRequest(path, {method: 'POST', body})
    if (mounted) notice.value = message
    return true
  } catch (cause) { if (mounted) actionError.value = cause.message }
  finally {
    if (mounted) {
      await (tab.value === 'review' ? loadReview() : loadSnapshot())
      activeAction.value = ''
    }
  }
}
function sourceAction(source, action) {
  const base = '/sources/' + encodeURIComponent(source.id)
  if (action === 'run') return act(base + '/run', undefined, source.name + uiText(" 수집을 요청했습니다."))
  return act(base + '/enabled', {enabled: !source.enabled}, source.name + (source.enabled ? uiText(" 수집을 일시정지했습니다.") : uiText(" 수집을 재개했습니다.")))
}
async function decide(item, publish) {
  const body = {status: publish ? 'PUBLISHED' : 'REJECTED'}
  if (publish && !item.gameCode && reviewGames.value[item.id]) body.gameCode = reviewGames.value[item.id]
  const done = await act('/review/' + encodeURIComponent(item.id) + '/decision', body,
    publish ? uiText("소식을 승인해 공개했습니다.") : uiText("소식을 반려했습니다."))
  if (done) delete reviewGames.value[item.id]
}
function stopReads() { snapshotController?.abort(); reviewController?.abort(); gamesController?.abort() }
watch([() => session.isAdmin, () => session.adminAccessBlocked], async ([admin, blocked]) => {
  stopReads()
  snapshot.value = null
  reviewItems.value = []
  reviewGames.value = {}
  notice.value = ''
  actionError.value = ''
  if (!admin || blocked) return
  loadSnapshot()
  if (tab.value === 'review') loadReview()
  const controller = gamesController = new AbortController()
  try { games.value = await request('/games', {signal: controller.signal}) }
  catch { /* Game codes remain available in the operations response. */ }
}, {immediate: true})
watch([tab, reviewPage], () => {
  notice.value = ''
  actionError.value = ''
  if (tab.value === 'review' && session.isAdmin) loadReview()
})
watch(locale,()=>{if(tab.value==='review'&&session.isAdmin)loadReview()})
onMounted(() => {
  mounted = true
  timer = window.setInterval(refreshWhenVisible, 60000)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  mounted = false
  clearInterval(timer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
  stopReads()
})
</script>
<template>
  <div class="admin-page">
    <header class="page-heading"><h1>{{ $t("서버 관리") }}</h1></header>
    <section v-if="!session.ready" class="state" role="status">{{ $t("로그인 상태를 확인하는 중입니다.") }}</section>
    <section v-else-if="!session.account" class="state"><p>{{ $t("관리자 계정으로 로그인해 주세요.") }}</p><RouterLink :to="{name: 'login', query: {to: 'admin'}}">{{ $t("로그인") }}</RouterLink></section>
    <p v-else-if="!session.isAdmin" role="alert" class="state">{{ $t("관리자 권한이 필요합니다.") }}</p>
    <AdminAccess v-else-if="session.adminAccessBlocked" />
    <template v-else>
      <nav class="game-tabs admin-tabs" :aria-label="$t('관리 메뉴')"><button v-for="(title, key) in tabs" :key="key" :aria-pressed="tab === key" :disabled="!!activeAction || catalogBusy" @click="selectTab(key)">{{ pt(title) }}</button></nav>
      <div class="ops-heading"><h2>{{ pt(tabs[tab]) }}</h2>
        <button v-if="['overview','sources','review'].includes(tab)" class="secondary" :disabled="!!activeAction || (tab === 'review' ? reviewBusy : snapshotBusy)" @click="refresh">{{ $t("새로고침") }}</button>
      </div>
      <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
      <p v-if="actionError" role="alert" class="inline-error">{{ actionError }}</p>
      <template v-if="['posts','stores','users','server'].includes(tab)">
        <AdminCommunityReports v-if="tab==='posts'"/>
        <AdminTools :tab="tab"/>
      </template>
      <AdminCatalog v-else-if="tab === 'catalog'" ref="catalogPanel" :games="games" @editing="catalogBusy=$event.busy" />
      <AdminReleases v-else-if="tab==='releases'" ref="releasesPanel" @busy="catalogBusy=$event"/>
      <template v-else-if="tab !== 'review'">
        <AdminProviders v-if="tab==='sources'"/>
        <AdminXSource v-if="tab==='sources'" :disabled="!!activeAction && activeAction!=='subscribe'"
          @saving="value=>{activeAction=value?'subscribe':''}" @saved="onSubscriptionSaved"/>
        <p v-if="snapshotError" role="alert" class="inline-error">{{ snapshotError }}</p>
        <p v-if="snapshotBusy && !snapshot" role="status" class="state">{{ $t("운영 상태를 불러오는 중입니다.") }}</p>
        <template v-if="snapshot">
          <p class="update-time">{{ $t("마지막 정상 응답") }} <time :datetime="checkedAt">{{ dateTime(checkedAt) }}</time></p>
          <template v-if="tab === 'overview'">
            <div class="ops-grid">
              <section class="ops-card"><h3>{{ $t("JVM 힙 메모리") }}</h3>
                <p class="reading">{{ bytes(snapshot.jvmUsedBytes) }} <span>{{ $t("사용") }}</span></p>
                <meter v-if="snapshot.jvmMaxBytes > 0 && snapshot.jvmUsedBytes != null" :value="snapshot.jvmUsedBytes" min="0" :max="snapshot.jvmMaxBytes" :aria-label="$t('JVM 힙 메모리 사용량')"></meter>
                <small>{{ $t("최대") }} {{ bytes(snapshot.jvmMaxBytes) }}</small>
              </section>
              <section class="ops-card"><h3>{{ $t("데이터 디스크") }}</h3>
                <p class="reading">{{ bytes(snapshot.diskUsableBytes) }} <span>{{ $t("사용 가능") }}</span></p>
                <meter v-if="snapshot.diskTotalBytes > 0 && diskUsed != null" :value="diskUsed" min="0" :max="snapshot.diskTotalBytes" :aria-label="$t('디스크 사용량')"></meter>
                <small>{{ $t("전체") }} {{ bytes(snapshot.diskTotalBytes) }}</small>
              </section>
              <section class="ops-card"><h3>{{ $t("수집 워커") }}</h3>
                <dl><div><dt>{{ $t("마지막 신호") }}</dt><dd>{{ dateTime(snapshot.workerHeartbeatAt) || $t("수신 기록 없음") }}</dd></div>
                  <div v-if="snapshot.workerStartedAt"><dt>{{ $t("워커 시작") }}</dt><dd>{{ dateTime(snapshot.workerStartedAt) }}</dd></div></dl>
                <p v-if="snapshot.workerRestartRequestedAt" class="update-time">{{ $t("재시작 요청") }} {{ dateTime(snapshot.workerRestartRequestedAt) }}</p>
                <button class="secondary" :disabled="!!activeAction || !!snapshot.workerRestartRequestedAt" @click="act('/worker/restart', undefined, $t('워커에 재시작을 요청했습니다.'))">{{ snapshot.workerRestartRequestedAt ? $t("재시작 요청 대기") : $t("워커 재시작 요청") }}</button>
              </section>
            </div>
            <section class="ops-card card-counts"><h3>{{ $t("게임별 도감 카드") }}</h3>
              <dl v-if="gameCounts.length"><div v-for="[code, count] in gameCounts" :key="code"><dt>{{ gameName(code) }}</dt><dd>{{ count.toLocaleString(locale) }}{{ $t("장") }}</dd></div></dl>
              <p v-else class="muted">{{ $t("집계 데이터가 없습니다.") }}</p>
            </section>
          </template>
          <div v-else-if="sources.length" class="source-grid">
            <article v-for="source in sources" :key="source.id" class="ops-card source-card">
              <div class="ops-heading"><h3>{{ source.name }}</h3><span class="label-tag">{{ states[source.state] || source.state }}</span></div>
              <p class="update-time">{{ source.gameCode ? gameName(source.gameCode) : $t("공통") }} · {{ providerName(source.provider) }}</p>
              <dl>
                <div><dt>{{ $t("최근 시작") }}</dt><dd>{{ dateTime(source.lastStartedAt) || $t("기록 없음") }}</dd></div>
                <div><dt>{{ $t("최근 성공") }}</dt><dd>{{ dateTime(source.lastSuccessAt) || $t("기록 없음") }}</dd></div>
                <div v-if="source.lastSuccessAt && source.lastCount != null"><dt>{{ $t("최근 수집") }}</dt><dd>{{ source.lastCount }}{{ $t("건") }}<span v-if="source.addedCount != null"> {{ $t("· 신규") }} {{ source.addedCount }}{{ $t("건") }}</span></dd></div>
                <div><dt>{{ $t("다음 수집") }}</dt><dd>{{ source.enabled ? dateTime(source.nextFetchAt) || $t("일정 미정") : $t("일시정지") }}</dd></div>
                <div v-if="source.runRequestedAt"><dt>{{ $t("수동 요청") }}</dt><dd>{{ dateTime(source.runRequestedAt) }}</dd></div>
              </dl>
              <div v-if="source.lastError || source.lastErrorAt" class="source-error">
                <strong>{{ $t("마지막 오류") }}</strong> <time v-if="source.lastErrorAt" :datetime="source.lastErrorAt">{{ dateTime(source.lastErrorAt) }}</time>
                <p v-if="source.lastError">{{ source.lastError }}</p>
              </div>
              <p v-if="source.policyNote">{{ source.policyNote }}</p>
              <div v-else class="ops-actions">
                <form @submit.prevent="act('/sources/'+source.id+'/interval',{seconds:Number(intervals[source.id]??source.intervalSeconds)},$t('수집 주기를 저장했습니다.'))"><label>{{ $t('수집 주기(초)') }}<input type="number" min="1" max="2592000" step="1" required :value="intervals[source.id]??source.intervalSeconds" @input="intervals[source.id]=$event.target.value"></label><button class="secondary" :disabled="!!activeAction">{{ $t('저장') }}</button></form>
                <button class="secondary" :disabled="!!activeAction" @click="sourceAction(source, 'enabled')">{{ source.enabled ? $t("일시정지") : $t("수집 재개") }}</button>
                <button class="primary" :disabled="!!activeAction || !source.enabled || ['QUEUED','RUNNING'].includes(source.state)" @click="sourceAction(source, 'run')">{{ $t("지금 수집") }}</button>
              </div>
            </article>
          </div>
          <p v-else class="state">{{ $t("등록된 수집 출처가 없습니다.") }}</p>
        </template>
      </template>
      <template v-else>
        <p v-if="reviewError" class="inline-error" role="alert">{{ reviewError }}</p>
        <p v-else-if="reviewBusy" class="state" role="status">{{ $t("검수 대기열을 불러오는 중입니다.") }}</p>
        <p v-else-if="!reviewItems.length" class="state">{{ $t("검수 대기 중인 소식이 없습니다.") }}</p>
        <template v-else>
          <p class="update-time">{{ $t("대기 중") }} {{ reviewTotal }}{{ $t("건") }}</p>
          <div class="news-list"><NewsItem v-for="item in reviewItems" :key="item.id" :item="item" :games="games" review>
            <label v-if="!item.gameCode" class="review-game">{{ $t("게시 게임") }}
              <select :value="reviewGames[item.id] || ''" :disabled="!!activeAction" @change="reviewGames[item.id] = $event.target.value">
                <option value="">{{ $t("공통 · 게임 미지정") }}</option>
                <option v-for="game in games" :key="game.code" :value="game.code">{{ gameName(game.code,game.name) }}</option>
              </select>
            </label>
            <div class="ops-actions"><button class="primary" :disabled="!!activeAction" @click="decide(item, true)">{{ $t("승인·공개") }}</button>
              <button class="secondary" :disabled="!!activeAction" @click="decide(item, false)">{{ $t("반려") }}</button></div>
          </NewsItem></div>
        </template>
        <nav v-if="reviewPages > 1" class="pagination" :aria-label="$t('검수 대기 페이지')">
          <button class="secondary" :disabled="!!activeAction || reviewBusy || reviewPage === 0" @click="reviewPage--">{{ $t("이전") }}</button><span>{{ reviewPage + 1 }} / {{ reviewPages }}</span>
          <button class="secondary" :disabled="!!activeAction || reviewBusy || reviewPage + 1 >= reviewPages" @click="reviewPage++">{{ $t("다음") }}</button>
        </nav>
      </template>
    </template>
  </div>
</template>
