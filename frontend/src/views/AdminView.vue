<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request } from '../api'
import { useSession } from '../stores/session'
import { bytes, dateTime, providerName } from '../presentation'
import NewsItem from '../components/NewsItem.vue'

const session = useSession()
const tab = ref('overview')
const tabs = {overview: '서버 상태', sources: '수집 출처', review: '검수 대기'}
const states = {IDLE: '대기', RUNNING: '수집 중', OK: '수집 성공', ERROR: '수집 오류', BLOCKED: '수집 차단', QUEUED: '실행 예약', PAUSED: '일시정지'}
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
const gameName = code => games.value.find(game => game.code === code)?.name || code
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
  if (!session.isAdmin) return
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
  if (!session.isAdmin) return
  reviewController?.abort()
  const controller = reviewController = new AbortController()
  reviewBusy.value = true
  reviewError.value = ''
  try {
    const query = new URLSearchParams({page: reviewPage.value, size: reviewSize})
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
function refreshWhenVisible() {
  if (document.visibilityState === 'visible' && session.isAdmin && tab.value !== 'review' &&
      !activeAction.value && !snapshotBusy.value) loadSnapshot()
}
async function act(path, body, message) {
  if (!session.isAdmin || activeAction.value) return
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
  if (action === 'run') return act(base + '/run', undefined, source.name + ' 수집을 요청했습니다.')
  return act(base + '/enabled', {enabled: !source.enabled}, source.name + (source.enabled ? ' 수집을 일시정지했습니다.' : ' 수집을 재개했습니다.'))
}
async function decide(item, publish) {
  const body = {status: publish ? 'PUBLISHED' : 'REJECTED'}
  if (publish && !item.gameCode && reviewGames.value[item.id]) body.gameCode = reviewGames.value[item.id]
  const done = await act('/review/' + encodeURIComponent(item.id) + '/decision', body,
    publish ? '소식을 승인해 공개했습니다.' : '소식을 반려했습니다.')
  if (done) delete reviewGames.value[item.id]
}
function stopReads() { snapshotController?.abort(); reviewController?.abort(); gamesController?.abort() }
watch(() => session.isAdmin, async admin => {
  stopReads()
  snapshot.value = null
  reviewItems.value = []
  reviewGames.value = {}
  notice.value = ''
  actionError.value = ''
  if (!admin) return
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
    <header class="page-heading"><h1>서버 관리</h1></header>
    <section v-if="!session.ready" class="state" role="status">로그인 상태를 확인하는 중입니다.</section>
    <section v-else-if="!session.account" class="state"><p>관리자 계정으로 로그인해 주세요.</p><RouterLink :to="{name: 'login', query: {to: 'admin'}}">로그인</RouterLink></section>
    <p v-else-if="!session.isAdmin" role="alert" class="state">관리자 권한이 필요합니다.</p>
    <template v-else>
      <nav class="game-tabs admin-tabs" aria-label="관리 메뉴"><button v-for="(title, key) in tabs" :key="key" :aria-pressed="tab === key" :disabled="!!activeAction" @click="tab = key">{{ title }}</button></nav>
      <div class="ops-heading"><h2>{{ tabs[tab] }}</h2>
        <button class="secondary" :disabled="!!activeAction || (tab === 'review' ? reviewBusy : snapshotBusy)" @click="refresh">새로고침</button>
      </div>
      <p v-if="notice" class="success-message" role="status">{{ notice }}</p>
      <p v-if="actionError" role="alert" class="inline-error">{{ actionError }}</p>
      <template v-if="tab !== 'review'">
        <p v-if="snapshotError" role="alert" class="inline-error">{{ snapshotError }}</p>
        <p v-if="snapshotBusy && !snapshot" role="status" class="state">운영 상태를 불러오는 중입니다.</p>
        <template v-if="snapshot">
          <p class="update-time">마지막 정상 응답 <time :datetime="checkedAt">{{ dateTime(checkedAt) }}</time></p>
          <template v-if="tab === 'overview'">
            <div class="ops-grid">
              <section class="ops-card"><h3>JVM 힙 메모리</h3>
                <p class="reading">{{ bytes(snapshot.jvmUsedBytes) }} <span>사용</span></p>
                <meter v-if="snapshot.jvmMaxBytes > 0 && snapshot.jvmUsedBytes != null" :value="snapshot.jvmUsedBytes" min="0" :max="snapshot.jvmMaxBytes" aria-label="JVM 힙 메모리 사용량"></meter>
                <small>최대 {{ bytes(snapshot.jvmMaxBytes) }}</small>
              </section>
              <section class="ops-card"><h3>데이터 디스크</h3>
                <p class="reading">{{ bytes(snapshot.diskUsableBytes) }} <span>사용 가능</span></p>
                <meter v-if="snapshot.diskTotalBytes > 0 && diskUsed != null" :value="diskUsed" min="0" :max="snapshot.diskTotalBytes" aria-label="디스크 사용량"></meter>
                <small>전체 {{ bytes(snapshot.diskTotalBytes) }}</small>
              </section>
              <section class="ops-card"><h3>수집 워커</h3>
                <dl><div><dt>마지막 신호</dt><dd>{{ dateTime(snapshot.workerHeartbeatAt) || '수신 기록 없음' }}</dd></div>
                  <div v-if="snapshot.workerStartedAt"><dt>워커 시작</dt><dd>{{ dateTime(snapshot.workerStartedAt) }}</dd></div></dl>
                <p v-if="snapshot.workerRestartRequestedAt" class="update-time">재시작 요청 {{ dateTime(snapshot.workerRestartRequestedAt) }}</p>
                <button class="secondary" :disabled="!!activeAction || !!snapshot.workerRestartRequestedAt" @click="act('/worker/restart', undefined, '워커에 재시작을 요청했습니다.')">{{ snapshot.workerRestartRequestedAt ? '재시작 요청 대기' : '워커 재시작 요청' }}</button>
              </section>
            </div>
            <section class="ops-card card-counts"><h3>게임별 도감 카드</h3>
              <dl v-if="gameCounts.length"><div v-for="[code, count] in gameCounts" :key="code"><dt>{{ gameName(code) }}</dt><dd>{{ count.toLocaleString('ko-KR') }}장</dd></div></dl>
              <p v-else class="muted">집계 데이터가 없습니다.</p>
            </section>
          </template>
          <div v-else-if="sources.length" class="source-grid">
            <article v-for="source in sources" :key="source.id" class="ops-card source-card">
              <div class="ops-heading"><h3>{{ source.name }}</h3><span class="label-tag">{{ states[source.state] || source.state }}</span></div>
              <p class="update-time">{{ source.gameCode ? gameName(source.gameCode) : '공통' }} · {{ providerName(source.provider) }}</p>
              <dl>
                <div><dt>최근 시작</dt><dd>{{ dateTime(source.lastStartedAt) || '기록 없음' }}</dd></div>
                <div><dt>최근 성공</dt><dd>{{ dateTime(source.lastSuccessAt) || '기록 없음' }}</dd></div>
                <div v-if="source.lastSuccessAt && source.lastCount != null"><dt>최근 수집</dt><dd>{{ source.lastCount }}건<span v-if="source.addedCount != null"> · 신규 {{ source.addedCount }}건</span></dd></div>
                <div><dt>다음 수집</dt><dd>{{ source.enabled ? dateTime(source.nextFetchAt) || '일정 미정' : '일시정지' }}</dd></div>
                <div v-if="source.runRequestedAt"><dt>수동 요청</dt><dd>{{ dateTime(source.runRequestedAt) }}</dd></div>
              </dl>
              <div v-if="source.lastError || source.lastErrorAt" class="source-error">
                <strong>마지막 오류</strong> <time v-if="source.lastErrorAt" :datetime="source.lastErrorAt">{{ dateTime(source.lastErrorAt) }}</time>
                <p v-if="source.lastError">{{ source.lastError }}</p>
              </div>
              <div class="ops-actions">
                <button class="secondary" :disabled="!!activeAction" @click="sourceAction(source, 'enabled')">{{ source.enabled ? '일시정지' : '수집 재개' }}</button>
                <button class="primary" :disabled="!!activeAction || !source.enabled || ['QUEUED','RUNNING'].includes(source.state)" @click="sourceAction(source, 'run')">지금 수집</button>
              </div>
            </article>
          </div>
          <p v-else class="state">등록된 수집 출처가 없습니다.</p>
        </template>
      </template>
      <template v-else>
        <p v-if="reviewError" class="inline-error" role="alert">{{ reviewError }}</p>
        <p v-else-if="reviewBusy" class="state" role="status">검수 대기열을 불러오는 중입니다.</p>
        <p v-else-if="!reviewItems.length" class="state">검수 대기 중인 소식이 없습니다.</p>
        <template v-else>
          <p class="update-time">대기 중 {{ reviewTotal }}건</p>
          <div class="news-list"><NewsItem v-for="item in reviewItems" :key="item.id" :item="item" :games="games" review>
            <label v-if="!item.gameCode" class="review-game">게시 게임
              <select :value="reviewGames[item.id] || ''" :disabled="!!activeAction" @change="reviewGames[item.id] = $event.target.value">
                <option value="">공통 · 게임 미지정</option>
                <option v-for="game in games" :key="game.code" :value="game.code">{{ game.name }}</option>
              </select>
            </label>
            <div class="ops-actions"><button class="primary" :disabled="!!activeAction" @click="decide(item, true)">승인·공개</button>
              <button class="secondary" :disabled="!!activeAction" @click="decide(item, false)">반려</button></div>
          </NewsItem></div>
        </template>
        <nav v-if="reviewPages > 1" class="pagination" aria-label="검수 대기 페이지">
          <button class="secondary" :disabled="!!activeAction || reviewBusy || reviewPage === 0" @click="reviewPage--">이전</button><span>{{ reviewPage + 1 }} / {{ reviewPages }}</span>
          <button class="secondary" :disabled="!!activeAction || reviewBusy || reviewPage + 1 >= reviewPages" @click="reviewPage++">다음</button>
        </nav>
      </template>
    </template>
  </div>
</template>
