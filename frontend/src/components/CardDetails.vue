<script setup>
import { t as uiText, locale, localizedCard, editionName } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request, sourceLink } from '../api'
import { cardArtworks, preferredArtwork } from '../artwork'
import ArtworkCredit from './ArtworkCredit.vue'

const props = defineProps({ cardId: { type: [Number, String], required: true }, lazy: Boolean })
const host = ref()
const dialog = ref()
const card = ref(null)
const error = ref('')
const loading = ref(false)
const selectedArt = ref(null)
const failedImage=ref('')
const choices = computed(() => {
  const data = card.value
  const legacyUrl = data?.specs?.images?.[locale.value]
  return cardArtworks(data?.imageUrl || legacyUrl, data?.imageUrl ? data.imageLanguage : locale.value,
    data?.variants || [], failedImage.value)
})
const current = computed(() => choices.value.find(art => art.key === selectedArt.value) ||
  preferredArtwork(choices.value, locale.value))
const index = computed(() => choices.value.indexOf(current.value))
const effect=computed(()=>card.value?.specs?.texts?.[locale.value]||card.value?.effect)
const titleLanguage = computed(()=>card.value?.specs?.names?.[locale.value] ? locale.value : card.value?.language)
const effectLanguage = computed(()=>card.value?.specs?.texts?.[locale.value] ? locale.value : card.value?.effectLanguage)
const title = computed(() => localizedCard(card.value))
const editionLabels = { ko: "한국어판", en: "영어판", ja: "일본어판" }
const editions = computed(() => Object.entries(card.value?.specs?.names || {}).filter(([code]) => Object.prototype.hasOwnProperty.call(editionLabels, code)))
const originalName = computed(() => {
  const name = card.value?.originalName
  return name && name !== title.value && !editions.value.some(([, printedName]) => printedName === name) ? name : ''
})
const specs = computed(() => Object.entries(card.value?.specs || {}).filter(([key, value]) =>
    !['xid','pk','ej','names','texts','images','sources'].includes(key) && value != null && value !== '' &&
    !(card.value?.gameCode==='ONEPIECE' && ['productCode','imageProducts','imageSources'].includes(key))))
const names = { k: "종류", at: "속성", lv: "레벨", mk: "링크 마커", rc: "종족", sub: "유형", ps: "펜듈럼 스케일", pe: "펜듈럼 효과", atk: "공격력", def: "수비력", or: "읽기", nw: "수록 구분", pr: "출처", pd: "발매 정보", type: "유형", attribute: "속성", level: "레벨", race: "종족" }
function display(value) {
  if (typeof value === 'boolean') return value ? uiText("예") : uiText("아니요")
  if (Array.isArray(value)) return value.map(display).join(' · ')
  if (typeof value === 'object' && value !== null) return Object.entries(value).map(([k, v]) => (uiText(names[k]) || k) + ' ' + display(v)).join(' · ')
  return String(value ?? '')
}
let controller
let accordion
async function load() {
  controller?.abort()
  const run = new AbortController()
  controller = run
  card.value = null
  selectedArt.value = null
  failedImage.value = ''
  loading.value = true
  error.value = ''
  try {
    const result = await request('/cards/' + encodeURIComponent(props.cardId)+'?lang='+locale.value, { signal: run.signal })
    if (!run.signal.aborted) card.value = result
  }
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
watch([() => props.cardId,locale], () => { if (!props.lazy || accordion?.open) load() })
</script>

<template>
  <div ref="host" class="details-body">
    <p v-if="loading" class="muted" role="status">{{ $t("카드 상세를 불러오는 중입니다.") }}</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="secondary" @click="load">{{ $t("다시 시도") }}</button></div>
    <article v-else-if="card">
      <h1 v-if="!lazy" :lang="titleLanguage || ''">{{ title }}</h1>
      <div class="detail-grid">
        <div class="illustration">
          <button v-if="current?.src" type="button" class="localized-card" @click="dialog.showModal()"><img :src="current.src" :alt="title" @error="failedImage=$event.target.getAttribute('src')" loading="lazy" referrerpolicy="no-referrer"></button>
          <button v-else-if="current?.style" class="atlas" :style="current.style" type="button" :aria-label="title + $t(' 이미지 확대')" @click="dialog.showModal()"></button>
          <span v-else class="atlas missing">{{ $t("이미지 미등록") }}</span>
          <small v-if="current?.src || current?.style" class="edition-note" aria-live="polite">
            <ArtworkCredit label-image :language="current.language" :automatic="selectedArt===null" :printing="current.src && card.gameCode==='ONEPIECE' ? card : null"/>
          </small>
          <div v-if="choices.length > 1" class="variant-nav">
            <button type="button" :disabled="index === 0" @click="selectedArt=choices[index-1].key" :aria-label="$t('이전 일러스트')">‹</button>
            <span>{{ index + 1 }} / {{ choices.length }}</span>
            <button type="button" :disabled="index + 1 === choices.length" @click="selectedArt=choices[index+1].key" :aria-label="$t('다음 일러스트')">›</button>
          </div>
          <dialog ref="dialog" class="zoom" :aria-label="$t('카드 이미지 확대')" @click="e => { if (e.target === dialog) dialog.close() }">
            <img v-if="current?.src" :src="current.src" :alt="title" @error="failedImage=$event.target.getAttribute('src')" class="localized-large" referrerpolicy="no-referrer">
            <div v-else-if="current?.style" class="atlas large" :style="current.style" role="img" :aria-label="title"></div>
            <button class="secondary" type="button" @click="dialog.close()">{{ $t("닫기") }}</button>
          </dialog>
        </div>
        <div class="card-facts">
          <div v-if="titleLanguage!==locale"><small>{{ $t('표시된 카드명') }}</small><p>{{ editionName(titleLanguage) }}</p></div>
          <div v-if="originalName"><small>{{ $t("원문명") }}</small><p>{{ originalName }}</p></div>
          <div v-if="card.number"><small>{{ $t("카드 번호") }}</small><p>{{ card.number }}</p></div>
          <div v-for="[code, name] in editions" :key="code">
            <small>{{ $t(editionLabels[code]) }}</small>
            <p :lang="code"><a v-if="sourceLink(card.specs?.sources?.[code])" :href="sourceLink(card.specs.sources[code])" target="_blank" rel="noopener noreferrer">{{ name }}</a><template v-else>{{ name }}</template></p>
          </div>
          <div v-if="card.packName"><small>{{ $t("수록 팩") }}</small><p>{{ card.packName }}</p></div>
          <div v-if="card.releaseDate"><small>{{ $t("발매일") }}</small><p>{{ card.releaseDate }}</p></div>
          <div v-if="card.sourceName || sourceLink(card.sourceUrl)"><small>{{ $t("정보 출처") }}</small>
            <p><a v-if="sourceLink(card.sourceUrl)" :href="sourceLink(card.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ card.sourceName || $t("원문 보기") }}</a>
              <span v-else>{{ card.sourceName }}</span></p>
          </div>
          <div v-if="current?.rarity || card.rarity || card.variants?.[0]?.rarity"><small>{{ $t("레어도") }}</small><p>{{ current?.rarity || card.rarity || card.variants?.[0]?.rarity }}</p></div>
          <div class="lib-actions">
            <RouterLink :to="{name:'binder',query:{card:card.id}}">{{ $t("바인더에 담기") }}</RouterLink>
            <RouterLink :to="{name:'deck-new',query:{game:card.gameCode,card:card.id}}">{{ $t("이 카드로 덱 만들기") }}</RouterLink>
            <RouterLink v-if="lazy" :to="{ name: 'card', params: { id: card.id } }">{{ $t("상세 페이지 열기") }}</RouterLink>
          </div>
        </div>
      </div>
      <section v-if="effect" class="detail-section"><h3>{{ $t("카드 효과") }}</h3><small v-if="effectLanguage!==locale" class="edition-note">{{ editionName(effectLanguage) }}</small><p :lang="effectLanguage || ''">{{ effect }}</p></section>
      <dl v-if="specs.length" class="specs"><div v-for="[key, value] in specs" :key="key"><dt>{{ $t(names[key]) || key }}</dt><dd>{{ display(value) }}</dd></div></dl>
    </article>
  </div>
</template>

<style scoped>
.edition-note{display:block;color:var(--mu);margin:.35rem 0;font-size:.85rem}
.localized-card{background:transparent;border:0;padding:0}
.localized-card img,.localized-large{max-width:100%;max-height:70vh;object-fit:contain}
.variant-nav{font-variant-numeric:tabular-nums}
@media (pointer:coarse){.variant-nav button{min-width:44px;min-height:44px}}
</style>
