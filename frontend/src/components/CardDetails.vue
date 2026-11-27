<script setup>
import { t as uiText, locale, supportedLanguage } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request, sourceLink } from '../api'
import { cardArtworks } from '../artwork'
import { cardDetailLocale } from '../cardDetailLocale'
import {rarityBadges} from '../cardRarity'
import { pngSnapshot } from '../pngSnapshot'
import CardArtworkPicker from './CardArtworkPicker.vue'
import CardTextCredit from './CardTextCredit.vue'
import KoreanPrinting from './KoreanPrinting.vue'
import PngExport from './PngExport.vue'
import { pt } from '../pack'

const props = defineProps({ cardId: { type: [Number, String], required: true }, lazy: Boolean })
const host = ref()
const article = ref()
const card = ref(null)
const error = ref('')
const loading = ref(false)
const sourceOpen=ref(false), copied=ref(false)
const failedImages=ref([])
function imageFailed(url){if(url && !failedImages.value.includes(url))failedImages.value.push(url)}
const choices = computed(() => {
  const data = card.value
  const legacyUrl = data?.specs?.images?.[locale.value]
  const all=cardArtworks(data?.imageUrl,data?.imageLanguage,data?.variants || [],null,data?.imageBasis)
  if(legacyUrl && !all.some(art=>art.src===legacyUrl)){
    const [legacy]=cardArtworks(legacyUrl,locale.value,[],null)
    if(legacy)all.push({...legacy,key:'edition-'+locale.value,printing:{gameCode:data.gameCode,
      productCode:data.specs.productCode,imageProduct:data.specs.imageProducts?.[locale.value],imageSource:data.specs.imageSources?.[locale.value]}})
  }
  return all.filter(art=>!art.src || !failedImages.value.includes(art.src))
})
const localized=computed(()=>card.value ? cardDetailLocale(card.value,locale.value) : {})
const localCredit=computed(()=>({...localized.value,language:localized.value.nameLanguage}))
const title=computed(()=>localized.value.name || card.value?.number || pt('이 언어의 카드명 미등록'))
function referenceOnly(art){
  const printing=art.printing || card.value
  return !!art.src && (art.reference || (printing?.productCode && printing?.imageProduct &&
    printing.productCode!=='PROMO' && printing.productCode!==printing.imageProduct))
}
const localArt=computed(()=>{
  const art=choices.value.filter(a=>(a.src || a.style) && !referenceOnly(a))
  const local=art.filter(a=>a.language===locale.value)
  if(local.length)return local
  // A Japanese-numbered card can still show its own verified Japanese scan in the English reader.
  // An atlas position alone cannot establish the language or market of a printing.
  const region=card.value?.gameCode==='YUGIOH' && /-(JP|EN|KR)\d+[A-Z]?$/i.exec(card.value.number || '')?.[1]?.toUpperCase()
  return art.filter(a=>a.style && a.language===({JP:'ja',EN:'en',KR:'ko'})[region] && a.language)
})
const otherArt=computed(()=>choices.value.filter(art=>(art.src || art.style) && !localArt.value.includes(art)))
const rarities=computed(()=>rarityBadges(card.value,locale.value))
const numericStats=['atk','def','power','might','hp']
const facts=computed(()=>localized.value.facts.filter(fact=>!numericStats.includes(fact.key)))
const stats=computed(()=>localized.value.facts.filter(fact=>numericStats.includes(fact.key)))
const effectEditions=computed(()=>Object.entries(card.value?.specs?.texts || {}).filter(([lang,text])=>
  supportedLanguage(lang) && text && lang!==locale.value && text!==card.value?.effect))
const editionLabels = { ko:'한국어 카드명', en:'영어 카드명', ja:'일본어 카드명' }
const editions = computed(() => Object.entries(card.value?.specs?.names || {}).filter(([code,name]) => {
  if(!supportedLanguage(code) || !name)return false
  if(code!==locale.value)return true
  // Keep a distinct language-edition source when the primary title has no citation.
  return name===localized.value.name && !sourceLink(card.value.nameReferenceUrl) && !!sourceLink(card.value.specs?.sources?.[code])
}))
const originalName = computed(() => {
  const name = card.value?.originalName
  return name && name !== localized.value.name && !editions.value.some(([, printedName]) => printedName === name) ? name : ''
})
const catalogNameBasis={IMPORTED_LABEL:'기존 도감 표기',IMPORTED_ORIGINAL:'기존 도감 원문'}
const wikiSearch=computed(()=>{
  const c=card.value
  if(!c || (localized.value.name && (!c.effect || localized.value.effect)
      && !catalogNameBasis[c.nameBasis] && c.nameBasis!=='RELATED_PRINTING'))return ''
  const query=c.originalName || c.name
  return query ? 'https://namu.wiki/Search?q='+encodeURIComponent(query) : ''
})
const specs = computed(() => Object.entries(card.value?.specs || {}).filter(([key, value]) =>
    !['xid','pk','ej','names','texts','images','sources','nameBasis','referenceNames','referenceNameUrls','editionEvidence','koreanPrinting'].includes(key) && value != null && value !== '' &&
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
let copyTimer
function endPress(){clearTimeout(copyTimer)}
async function copyName(event){
  if(!localized.value.name)return
  endPress()
  const node=event.currentTarget
  try { await navigator.clipboard.writeText(localized.value.name);copied.value=true }
  catch {const range=document.createRange();range.selectNodeContents(node);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range)}
}
function beginPress(event){
  endPress()
  if(!localized.value.name || event.button!==0)return
  const target=event.currentTarget
  copyTimer=setTimeout(()=>copyName({currentTarget:target}),600)
}
function snapshot(width){return pngSnapshot(article.value,title.value,card.value.number || '',width)}
async function load() {
  controller?.abort()
  const run = new AbortController()
  controller = run
  card.value = null
  endPress();sourceOpen.value=false;copied.value=false
  failedImages.value = []
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
onBeforeUnmount(() => { endPress();controller?.abort(); accordion?.removeEventListener('toggle', onToggle) })
watch([() => props.cardId,locale], () => {
  if (!props.lazy || accordion?.open) load()
  else { controller?.abort(); card.value=null;loading.value=false;error.value='' }
})
</script>

<template>
  <div ref="host" class="details-body">
    <p v-if="loading" class="muted" role="status">{{ $t("카드 상세를 불러오는 중입니다.") }}</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="secondary" @click="load">{{ $t("다시 시도") }}</button></div>
    <template v-else-if="card">
      <article ref="article" class="card-reader">
        <header class="reader-title" data-png-skip>
          <span v-if="card.number && localized.name" class="reader-number">{{ card.number }}</span>
          <component :is="lazy?'h3':'h1'" :lang="localized.nameLanguage || locale" @pointerdown="beginPress" @pointerup="endPress" @pointercancel="endPress" @pointerleave="endPress" @contextmenu="e=>{if(localized.name){e.preventDefault();copyName(e)}}">{{ title }}</component>
          <small v-if="!localized.name && card.number" class="muted">{{ pt('이 언어의 카드명 미등록') }}</small>
          <small v-if="copied" role="status" class="muted">{{ pt('카드명을 복사했습니다.') }}</small>
        </header>
        <div class="detail-grid">
          <CardArtworkPicker :card="card" :title="title" :choices="localArt" @failed="imageFailed"/>
          <dl class="reader-facts">
            <div v-for="fact in facts" :key="fact.key"><dt>{{ fact.label }}</dt><dd>{{ fact.value }}</dd></div>
            <div v-if="rarities.length" class="rarities-row"><dt>{{ $t('레어도') }}</dt><dd class="reader-rarities">
              <span v-for="r in rarities" :key="r.code || r.label"><b v-if="r.code">{{ r.code }}</b>{{ r.label }}</span>
            </dd></div>
            <div v-if="card.releaseDate"><dt>{{ $t('발매일') }}</dt><dd><time :datetime="card.releaseDate">{{ card.releaseDate }}</time></dd></div>
          </dl>
        </div>
        <section class="detail-section">
          <h3>{{ $t('카드 효과') }}</h3>
          <p v-if="localized.effect" :lang="localized.effectLanguage">{{ localized.effect }}</p>
          <p v-else class="muted">{{ pt('이 언어의 효과 텍스트 미등록') }}</p>
          <CardTextCredit v-if="localized.effect" :card="localCredit" effect/>
        </section>
        <dl v-if="stats.length" class="reader-stats"><div v-for="fact in stats" :key="fact.key"><dt>{{ fact.label }}</dt><dd>{{ fact.value }}</dd></div></dl>
      </article>
      <details class="reader-source" @toggle="sourceOpen=$event.currentTarget.open">
        <summary>{{ pt('원문·출처') }}<span aria-hidden="true">⌄</span></summary>
        <div v-if="sourceOpen" class="source-content">
          <CardArtworkPicker v-if="otherArt.length" :choices="otherArt" :card="card" :title="card.originalName || card.name || title" original @failed="imageFailed"/>
          <div class="card-facts">
            <div v-if="card.name && !localized.name && card.name!==originalName && !editions.some(([,name])=>name===card.name)"><small>{{ $t('카드명') }}</small><p :lang="card.language || ''">{{ card.name }}</p></div>
            <CardTextCredit :card="card" detailed link/>
            <div v-if="originalName"><small>{{ $t('원문명') }}</small><p>{{ originalName }}</p></div>
            <div v-for="[code,name] in editions" :key="code">
              <small>{{ pt(editionLabels[code]) }}</small>
              <p :lang="code"><a v-if="sourceLink(card.specs?.sources?.[code])" :href="sourceLink(card.specs.sources[code])" target="_blank" rel="noopener noreferrer">{{ name }}</a><template v-else>{{ name }}</template></p>
            </div>
            <div v-if="card.effect && !localized.effect"><small>{{ $t('카드 효과') }}</small><p :lang="card.effectLanguage || ''" class="source-effect">{{ card.effect }}</p></div>
            <CardTextCredit :card="card" effect link detailed/>
            <div v-for="[code,text] in effectEditions" :key="'effect-'+code"><small>{{ $t('카드 효과') }} · {{ pt(({ko:'한국어',en:'영어',ja:'일본어'})[code]) }}</small><p :lang="code" class="source-effect">{{ text }}</p></div>
            <KoreanPrinting v-if="card.gameCode==='YUGIOH' && card.specs?.koreanPrinting" :printing="card.specs.koreanPrinting"/>
            <div v-if="card.packName"><small>{{ $t('수록 팩') }}</small><p>{{ card.packName }}</p></div>
            <div v-if="card.sourceName || sourceLink(card.sourceUrl)"><small>{{ $t('정보 출처') }}</small>
              <p><a v-if="sourceLink(card.sourceUrl)" :href="sourceLink(card.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ card.sourceName || $t('원문 보기') }}</a><span v-else>{{ card.sourceName }}</span></p>
            </div>
            <a v-if="wikiSearch" :href="wikiSearch" target="_blank" rel="noopener noreferrer">{{ pt('나무위키에서 검색') }}</a>
          </div>
          <dl v-if="specs.length" class="specs"><div v-for="[key,value] in specs" :key="key"><dt>{{ $t(names[key]) || key }}</dt><dd>{{ display(value) }}</dd></div></dl>
        </div>
      </details>
      <div class="reader-actions">
        <PngExport :key="card.id+'-'+locale" choose-width :name="[card.number,localized.name].filter(Boolean).join(' ')" :label="pt('카드 정보 PNG')" :render="snapshot"/>
        <div class="lib-actions">
          <RouterLink :to="{name:'binder',query:{card:card.id,lang:locale}}">{{ $t('바인더에 담기') }}</RouterLink>
          <RouterLink :to="{name:'deck-new',query:{game:card.gameCode,card:card.id,lang:locale}}">{{ $t('이 카드로 덱 만들기') }}</RouterLink>
          <RouterLink v-if="lazy" :to="{name:'card',params:{id:card.id},query:{lang:locale}}">{{ $t('상세 페이지 열기') }}</RouterLink>
        </div>
      </div>
    </template>
  </div>
</template>
<style scoped>
.reader-rarities{display:flex;flex-wrap:wrap;gap:4px}.reader-rarities span{display:inline-flex;align-items:baseline;gap:.35em;padding:2px 6px;border:1px solid var(--bd);border-radius:4px;color:var(--tx);font-size:.76rem;line-height:1.5}.reader-rarities b{color:var(--ac)}
.reader-title{margin:0 0 16px}.reader-title h1,.reader-title h3{margin:2px 0 0;font-size:clamp(1.25rem,3.1vw,1.85rem);line-height:1.25;letter-spacing:-.025em;word-break:keep-all;overflow-wrap:anywhere;user-select:text}
.reader-number{color:var(--mu);font-size:.8rem;font-variant-numeric:tabular-nums;letter-spacing:.035em}
.card-reader .detail-grid{grid-template-columns:minmax(90px,clamp(100px,29%,192px)) minmax(0,1fr);gap:clamp(12px,3vw,23px);align-items:start}
.reader-facts{min-width:0;margin:0}.reader-facts div{display:grid;grid-template-columns:minmax(4em,.65fr) minmax(0,1fr);gap:8px;align-items:baseline;padding:5px 0;border-bottom:1px solid var(--bd)}
.reader-facts div:first-child{padding-top:0}.reader-facts dt,.reader-facts dd{margin:0;overflow-wrap:anywhere;line-height:1.35}.reader-facts dt{color:var(--mu);font-size:.78rem}.reader-facts dd{font-size:.9rem;font-weight:580;font-variant-numeric:tabular-nums}
.detail-section h3{font-size:1rem;margin:0 0 6px}.detail-section .card-text-credit{margin-top:5px}
.reader-stats{display:flex;gap:0 24px;flex-wrap:wrap;margin:12px 0 0}.reader-stats div{display:flex;align-items:baseline;gap:8px}.reader-stats dt{font-size:.8rem;color:var(--mu)}.reader-stats dd{margin:0;font-weight:700;font-variant-numeric:tabular-nums}
.reader-source{border-block:1px solid var(--bd);margin-top:18px}.reader-source>summary{display:flex;align-items:center;justify-content:space-between;padding:7px 0;min-height:44px;gap:12px;background:transparent;box-shadow:none;font-weight:600;font-size:.9rem;cursor:pointer;list-style:none}
.reader-source[open]>summary span{transform:rotate(180deg)}.source-content{display:grid;gap:12px;padding:6px 0 16px}.source-content>.illustration{max-width:150px}.source-content .specs{margin-top:0}.source-effect{white-space:pre-line}.reader-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px 16px;margin-top:12px}.reader-actions .lib-actions{display:flex;flex-wrap:wrap;gap:4px 12px;margin:0;font-size:.84rem}
@media(max-width:500px){
  .card-reader .detail-grid{grid-template-columns:minmax(90px,36%) minmax(0,1fr);gap:12px}
  .reader-facts div{grid-template-columns:minmax(3em,.55fr) minmax(0,1fr);gap:5px;padding:4px 0}
  .reader-facts .rarities-row{display:block}.reader-title{margin-bottom:12px}.reader-actions .lib-actions a{padding-block:6px}
}
</style>
