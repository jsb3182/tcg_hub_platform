<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { mediaPath, request } from '../api'

const props = defineProps({ cardId: { type: [Number, String], required: true }, lazy: Boolean })
const host = ref()
const dialog = ref()
const card = ref(null)
const error = ref('')
const loading = ref(false)
const index = ref(0)
const current = computed(() => card.value?.variants?.[index.value])
const image = computed(() => current.value?.image)
const tileStyle = computed(() => {
  const tile = image.value
  const url = mediaPath(tile?.url)
  if (!url || !Number.isInteger(tile.col) || tile.col < 0 || tile.col > 3 ||
      !Number.isInteger(tile.row) || tile.row < 0 || tile.row > 2) return null
  return {
    backgroundImage: 'url("' + url.replace(/"/g, '%22') + '")',
    backgroundPosition: (tile.col * 100 / 3) + '% ' + (tile.row * 50) + '%',
    aspectRatio: tile.cellWidth > 0 && tile.cellHeight > 0 ? tile.cellWidth + ' / ' + tile.cellHeight : '300 / 438',
  }
})
const title = computed(() => card.value?.name || card.value?.originalName || '이름 미정')
const specs = computed(() => Object.entries(card.value?.specs || {}).filter(([key, value]) =>
  key !== 'xid' && key !== 'pk' && value != null && value !== ''))
const names = { k: '종류', at: '속성', lv: '레벨', mk: '링크 마커', rc: '종족', sub: '유형', ps: '펜듈럼 스케일', pe: '펜듈럼 효과', atk: '공격력', def: '수비력', or: '읽기', nw: '수록 구분', pr: '출처', pd: '발매 정보', ej: '일본어 효과', type: '유형', attribute: '속성', level: '레벨', race: '종족' }
function display(value) {
  if (typeof value === 'boolean') return value ? '예' : '아니요'
  if (Array.isArray(value)) return value.map(display).join(' · ')
  if (typeof value === 'object' && value !== null) return Object.entries(value).map(([k, v]) => (names[k] || k) + ' ' + display(v)).join(' · ')
  return String(value ?? '')
}
let controller
let accordion
async function load() {
  controller?.abort()
  const run = new AbortController()
  controller = run
  card.value = null
  index.value = 0
  loading.value = true
  error.value = ''
  try { card.value = await request('/cards/' + encodeURIComponent(props.cardId), { signal: run.signal }) }
  catch (cause) { if (!run.signal.aborted) error.value = cause.message }
  finally { if (!run.signal.aborted) loading.value = false }
}
function onToggle() { if (accordion?.open && !card.value && !loading.value) load() }
onMounted(() => {
  if (props.lazy) {
    accordion = host.value.closest('details')
    accordion?.addEventListener('toggle', onToggle)
    onToggle()
  } else load()
})
onBeforeUnmount(() => { controller?.abort(); accordion?.removeEventListener('toggle', onToggle) })
watch(() => props.cardId, () => { if (!props.lazy || accordion?.open) load() })
</script>

<template>
  <div ref="host" class="details-body">
    <p v-if="loading" class="muted" role="status">카드 상세를 불러오는 중입니다.</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="secondary" @click="load">다시 시도</button></div>
    <article v-else-if="card">
      <h1 v-if="!lazy">{{ title }}</h1>
      <div class="detail-grid">
        <div class="illustration">
          <button v-if="tileStyle" class="atlas" :style="tileStyle" type="button" :aria-label="title + ' 이미지 확대'" @click="dialog.showModal()"></button>
          <span v-else class="atlas missing">이미지 미등록</span>
          <div v-if="card.variants.length > 1" class="variant-nav">
            <button type="button" :disabled="index === 0" @click="index--" aria-label="이전 일러스트">‹</button>
            <span>{{ index + 1 }} / {{ card.variants.length }}</span>
            <button type="button" :disabled="index + 1 === card.variants.length" @click="index++" aria-label="다음 일러스트">›</button>
          </div>
          <dialog ref="dialog" class="zoom" aria-label="카드 이미지 확대" @click="e => { if (e.target === dialog) dialog.close() }">
            <div class="atlas large" :style="tileStyle" role="img" :aria-label="title"></div>
            <button class="secondary" type="button" @click="dialog.close()">닫기</button>
          </dialog>
        </div>
        <div class="card-facts">
          <div v-if="card.originalName && card.originalName !== title"><small>원문명</small><p>{{ card.originalName }}</p></div>
          <div v-if="card.number"><small>카드 번호</small><p>{{ card.number }}</p></div>
          <div v-if="card.packName"><small>수록 팩</small><p>{{ card.packName }}</p></div>
          <div v-if="card.releaseDate"><small>발매일</small><p>{{ card.releaseDate }}</p></div>
          <div v-if="current?.rarity || card.rarity"><small>레어도</small><p>{{ current?.rarity || card.rarity }}</p></div>
          <RouterLink v-if="lazy" :to="{ name: 'card', params: { id: card.id } }">상세 페이지 열기</RouterLink>
        </div>
      </div>
      <section v-if="card.effect" class="detail-section"><h3>카드 효과</h3><p>{{ card.effect }}</p></section>
      <dl v-if="specs.length" class="specs"><div v-for="[key, value] in specs" :key="key"><dt>{{ names[key] || key }}</dt><dd>{{ display(value) }}</dd></div></dl>
    </article>
  </div>
</template>
