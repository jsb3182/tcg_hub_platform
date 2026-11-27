<script setup>
import { t as uiText, locale, localizedCard, supportedLanguage } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request, sourceLink } from '../api'
import { cardArtworks, preferredArtwork } from '../artwork'
import ArtworkCredit from './ArtworkCredit.vue'
import CardTextCredit from './CardTextCredit.vue'
import { pt } from '../pack'

const props = defineProps({ cardId: { type: [Number, String], required: true }, lazy: Boolean })
const host = ref()
const dialog = ref()
const article = ref()
const card = ref(null)
const error = ref('')
const loading = ref(false)
const selectedArt = ref(null)
const failedImage=ref('')
const choices = computed(() => {
  const data = card.value
  const legacyUrl = data?.specs?.images?.[locale.value]
  return cardArtworks(data?.imageUrl || legacyUrl, data?.imageUrl ? data.imageLanguage : locale.value,
    data?.variants || [], failedImage.value, data?.imageBasis)
})
const current = computed(() => choices.value.find(art => art.key === selectedArt.value) ||
  preferredArtwork(choices.value, locale.value))
const index = computed(() => choices.value.indexOf(current.value))
const effect=computed(()=>card.value?.effect ?? card.value?.specs?.texts?.[locale.value])
const titleLanguage = computed(()=>card.value?.language ?? (card.value?.specs?.names?.[locale.value] ? locale.value : null))
const effectLanguage = computed(()=>card.value?.effectLanguage ?? (card.value?.specs?.texts?.[locale.value] ? locale.value : null))
const title = computed(() => localizedCard(card.value))
const editionLabels = { ko:'한국어 카드명', en:'영어 카드명', ja:'일본어 카드명' }
const editions = computed(() => Object.entries(card.value?.specs?.names || {}).filter(([code,name]) => {
  if(!supportedLanguage(code) || !name)return false
  if(code!==locale.value)return true
  // Keep a distinct language-edition source when the primary title has no citation.
  return name===title.value && !sourceLink(card.value.nameReferenceUrl) && !!sourceLink(card.value.specs?.sources?.[code])
}))
const originalName = computed(() => {
  const name = card.value?.originalName
  return name && name !== title.value && !editions.value.some(([, printedName]) => printedName === name) ? name : ''
})
const catalogNameBasis={IMPORTED_LABEL:'기존 도감 표기',IMPORTED_ORIGINAL:'기존 도감 원문'}
const wikiSearch=computed(()=>{
  const c=card.value
  if(!c || (titleLanguage.value===locale.value && (!effect.value || effectLanguage.value===locale.value)
      && !catalogNameBasis[c.nameBasis] && c.nameBasis!=='RELATED_PRINTING'))return ''
  const query=c.originalName || c.name
  return query ? 'https://namu.wiki/Search?q='+encodeURIComponent(query) : ''
})
const specs = computed(() => Object.entries(card.value?.specs || {}).filter(([key, value]) =>
    !['xid','pk','ej','names','texts','images','sources','nameBasis','referenceNames','referenceNameUrls','editionEvidence'].includes(key) && value != null && value !== '' &&
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
watch([() => props.cardId,locale], () => {
  if (!props.lazy || accordion?.open) load()
  else { controller?.abort(); card.value=null;loading.value=false;error.value='' }
})
</script>

<template>
  <div ref="host" class="details-body">
    <p v-if="loading" class="muted" role="status">{{ $t("카드 상세를 불러오는 중입니다.") }}</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="secondary" @click="load">{{ $t("다시 시도") }}</button></div>
    <article v-else-if="card" ref="article">
      <h1 v-if="!lazy" :lang="titleLanguage || ''">{{ title }}</h1>
      <div class="detail-grid">
        <div class="illustration">
          <button v-if="current?.src" type="button" class="localized-card" @click="dialog.showModal()"><img :src="current.src" :alt="title" @error="failedImage=$event.target.getAttribute('src')" loading="lazy" referrerpolicy="no-referrer"></button>
          <button v-else-if="current?.style" class="atlas" :style="current.style" type="button" :aria-label="title + $t(' 이미지 확대')" @click="dialog.showModal()"></button>
          <span v-else class="atlas missing">{{ $t("이미지 미등록") }}</span>
          <small v-if="current?.src || current?.style" class="edition-note" aria-live="polite">
            <ArtworkCredit label-image :language="current.language" :automatic="selectedArt===null" :printing="current.src ? card : null"/>
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
          <CardTextCredit :card="card" detailed link/>
          <div v-if="originalName"><small>{{ $t("원문명") }}</small><p>{{ originalName }}</p></div>
          <div v-if="card.number"><small>{{ $t("카드 번호") }}</small><p>{{ card.number }}</p></div>
          <div v-for="[code, name] in editions" :key="code">
            <small>{{ pt(editionLabels[code]) }}</small>
            <p :lang="code"><a v-if="sourceLink(card.specs?.sources?.[code])" :href="sourceLink(card.specs.sources[code])" target="_blank" rel="noopener noreferrer">{{ name }}</a><template v-else>{{ name }}</template></p>
          </div>
          <div v-if="card.packName"><small>{{ $t("수록 팩") }}</small><p>{{ card.packName }}</p></div>
          <div v-if="card.releaseDate"><small>{{ $t("발매일") }}</small><p>{{ card.releaseDate }}</p></div>
          <div v-if="card.sourceName || sourceLink(card.sourceUrl)"><small>{{ $t("정보 출처") }}</small>
            <p><a v-if="sourceLink(card.sourceUrl)" :href="sourceLink(card.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ card.sourceName || $t("원문 보기") }}</a>
              <span v-else>{{ card.sourceName }}</span></p>
          </div>
          <a v-if="wikiSearch" :href="wikiSearch" target="_blank" rel="noopener noreferrer">{{ pt('나무위키에서 검색') }}</a>
          <div v-if="current?.rarity || card.rarity || card.variants?.[0]?.rarity"><small>{{ $t("레어도") }}</small><p>{{ current?.rarity || card.rarity || card.variants?.[0]?.rarity }}</p></div>
          <div class="lib-actions">
            <RouterLink :to="{name:'binder',query:{card:card.id,lang:locale}}">{{ $t("바인더에 담기") }}</RouterLink>
            <RouterLink :to="{name:'deck-new',query:{game:card.gameCode,card:card.id,lang:locale}}">{{ $t("이 카드로 덱 만들기") }}</RouterLink>
            <RouterLink v-if="lazy" :to="{ name: 'card', params: { id: card.id },query:{lang:locale} }">{{ $t("상세 페이지 열기") }}</RouterLink>
          </div>
        </div>
      </div>
      <section v-if="effect" class="detail-section"><h3>{{ $t("카드 효과") }}</h3><p :lang="effectLanguage || ''">{{ effect }}</p><CardTextCredit :card="card" effect link detailed/></section>
      <dl v-if="specs.length" class="specs"><div v-for="[key, value] in specs" :key="key"><dt>{{ $t(names[key]) || key }}</dt><dd>{{ display(value) }}</dd></div></dl>
    </article>
    <slot v-if="card && article" name="after-card" :card="card" :article="article"/>
  </div>
</template>

<style scoped>
.edition-note{display:block;color:var(--mu);margin:.35rem 0;font-size:.85rem}
.localized-card{background:transparent;border:0;padding:0}
.localized-card img,.localized-large{max-width:100%;max-height:70vh;object-fit:contain}
.variant-nav{font-variant-numeric:tabular-nums}
@media (pointer:coarse){.variant-nav button{min-width:44px;min-height:44px}}
</style>
