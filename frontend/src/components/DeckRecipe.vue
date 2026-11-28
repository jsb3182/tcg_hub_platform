<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { locale } from '../i18n'
import { deckName,sectionLabel, stateLabel } from '../library'
import { copies, groupRecipe, slots } from '../recipeLayout'
import { drawRecipe, rt } from '../recipeImage'
import DeckAnalysis from './DeckAnalysis.vue'
import LibraryThumbnail from './LibraryThumbnail.vue'
import CardTextCredit from './CardTextCredit.vue'
import ArtworkCredit from './ArtworkCredit.vue'
import PngExport from './PngExport.vue'
import {facetLabel,pt} from '../pack'
import DeckBanner from './DeckBanner.vue'

const props=defineProps({deck:{type:Object,required:true},gameName:String})
const query=ref(''),mode=ref('list'),images=ref(true),excludeSide=ref(false),limits=reactive({})
const details=ref(false),hideStock=ref(false)
const hasOwnership=computed(()=>props.deck.entries.some(e=>Number.isInteger(e.ownedCopies)))
const offsets=computed(()=>{
  const consumed=new Map(),out=new Map()
  for(const {entries} of groups.value)for(const e of entries){const before=consumed.get(e.cardId)||0;out.set(e,before);consumed.set(e.cardId,before+copies(e))}
  return out
})
function missing(entry,index){return Number.isInteger(entry.ownedCopies) && (offsets.value.get(entry)||0)+index>=entry.ownedCopies}
function limited(entry){return props.deck.regionalLimits?.violations?.find(v=>v.cardId===entry.cardId)?.limit}
const groups=computed(()=>groupRecipe(props.deck))
const rarities=computed(()=>new Map(props.deck.entries.map(entry=>[entry,facetLabel('rarity',entry.rarity,props.deck.gameCode)])))
const total=computed(()=>groups.value.reduce((n,g)=>n+g.total,0))
const hasSide=computed(()=>groups.value.some(g=>g.section==='SIDE' && g.total))
const name=computed(()=>deckName(props.deck))
const term=computed(()=>query.value.trim().normalize('NFKC').toLowerCase())
const shown=computed(()=>groups.value.map(group=>{
  const entries=term.value?group.entries.filter(e=>[e.name,e.number].some(s=>
    typeof s==='string' && s.normalize('NFKC').toLowerCase().includes(term.value))):group.entries
  const matched=entries.reduce((n,e)=>n+copies(e),0)
  return {...group,entries,matched,slots:mode.value==='gallery'?slots(entries,limits[group.section]||72):[]}
}))
const matchedCopies=computed(()=>shown.value.reduce((n,g)=>n+g.matched,0))
watch([query,()=>props.deck.id,()=>props.deck.gameCode],()=>{for(const key of Object.keys(limits)) delete limits[key]})
function exportImage(){
  return drawRecipe({name:name.value,game:props.gameName||props.deck.gameCode,groups:groups.value,excludeSide:!!(hasSide.value&&excludeSide.value),missing:hideStock.value?null:missing})
}
</script>
<template>
  <section class="lib-panel recipe-panel"><div class="lib-heading"><h2>{{ rt('덱 레시피') }}</h2></div>
    <div class="recipe-tools">
      <label class="recipe-search">{{ rt('덱에서 검색') }}<input v-model="query" type="search" :placeholder="rt('카드명 또는 번호')"></label>
      <div class="recipe-display"><div role="group" :aria-label="rt('덱 레시피')" class="recipe-switch">
        <button type="button" :aria-pressed="mode==='list'" @click="mode='list'">{{ rt('목록') }}</button>
        <button type="button" :aria-pressed="mode==='gallery'" @click="mode='gallery'">{{ rt('배열') }}</button>
      </div>
      <button v-if="mode==='list'" class="text-button" type="button" :aria-pressed="images" @click="images=!images">{{ rt(images?'이미지 숨기기':'이미지 보기') }}</button>
      <button type="button" class="text-button" :aria-pressed="details" @click="details=!details">{{ pt('상세') }}</button></div>
    </div>
    <article class="lib-recipe">
      <DeckBanner :deck="deck" :ordinal="deck.ordinal"/><h3 class="recipe-title">{{ name }}</h3><small>{{ gameName || deck.gameCode }} · {{ stateLabel(deck.state) }} · {{ total }}{{ rt('장') }}</small>
      <p v-if="term && !matchedCopies" class="muted" role="status">{{ rt('이 덱에는 일치하는 카드가 없습니다.') }}</p>
      <template v-for="group in shown" :key="group.section"><section v-if="!term || group.matched" class="recipe-section">
        <h4>{{ sectionLabel(group.section) }} <span>{{ group.total }}{{ rt('장') }}</span></h4>
        <p v-if="group.counts.length" class="recipe-counts" :aria-label="rt('유형별 장수')"><span v-for="[type,n] in group.counts" :key="type">{{ rt(type) }} {{ n }}</span></p>
        <small v-if="!group.entries.length">{{ rt('등록된 카드가 없습니다.') }}</small>
        <ul v-else-if="mode==='list'"><li v-for="(e,num) in group.entries" :key="[e.cardId,e.variantId,e.neuronArtwork].join('-')">
          <small v-if="details" class="recipe-index">{{ num+1 }}</small>
          <div class="lib-print"><LibraryThumbnail :placeholder="images" :image="images?e.image:null" :src="images && !(e.variantId && e.image)?e.imageUrl:undefined" :language="e.imageLanguage" :printing="e" v-slot="{art}">
            <span><span :lang="e.language || ''">{{ e.name }}</span><CardTextCredit :card="e"/><small>{{ e.number }}</small><small v-if="art?.reference || (art?.src && e.imageBasis==='SELECTED_ARTWORK')"><ArtworkCredit :language="art.language" :printing="e"/></small></span>
          </LibraryThumbnail></div><div class="recipe-quantity"><b>×{{ e.quantity }}</b><template v-if="details"><small>{{ rarities.get(e)||pt('레어도 미기재') }}</small>
            <small v-if="e.ownedCopies!=null">{{ pt('보유 수량') }} {{ e.ownedCopies }}</small></template></div>
        </li></ul>
        <template v-else>
          <ul class="recipe-tiles" :class="{'with-details':details}"><li v-for="{entry,index} in group.slots" :key="[entry.cardId,entry.variantId,entry.neuronArtwork,index].join('-')">
            <RouterLink :to="{name:'card',params:{id:entry.cardId},query:{lang:locale}}" :aria-label="entry.name">
              <LibraryThumbnail :image="entry.image" :src="entry.variantId&&entry.image?undefined:entry.imageUrl" :language="entry.imageLanguage" :printing="entry" v-slot="{art}">
                <span v-if="!art" class="recipe-art"><small>{{ rt('이미지 없음') }}</small></span>
                <span v-if="details" class="recipe-tags"><small v-if="missing(entry,index)" :title="pt('부족')">−</small><small v-if="limited(entry)!=null" :title="pt('대회 제한')">{{ limited(entry) }}</small>
                  <small v-else-if="rarities.get(entry) && rarities.get(entry).length<=4">{{ rarities.get(entry) }}</small></span>
                <strong :lang="entry.language || ''">{{ entry.name }}</strong><small>{{ entry.number }}</small><small v-if="art?.reference || (art?.src && entry.imageBasis==='SELECTED_ARTWORK')"><ArtworkCredit :printing="entry" :language="art.language" disable-link/></small>
                <CardTextCredit :card="entry"/>
              </LibraryThumbnail>
            </RouterLink>
          </li></ul>
          <button v-if="group.slots.length<group.matched" class="secondary recipe-more" type="button" @click="limits[group.section]=(limits[group.section]||72)+72">
            {{ rt('더 보기') }} · {{ group.slots.length }} / {{ group.matched }}
          </button>
        </template>
      </section></template>
    </article>
    <div class="recipe-export">
      <label v-if="hasSide" class="lib-check"><input type="checkbox" v-model="excludeSide">{{ rt('이미지에 사이드 제외') }}</label>
      <div class="recipe-export-buttons"><PngExport quick-save :render="exportImage" :name="name" :label="rt('PNG 저장')" :summary="[name,total+rt('장')].join(' · ')" :render-key="String(excludeSide)+'-'+hideStock">
        <label v-if="hasSide" class="lib-check"><input type="checkbox" v-model="excludeSide">{{ rt('이미지에 사이드 제외') }}</label>
        <label v-if="hasOwnership" class="lib-check"><input type="checkbox" v-model="hideStock">{{ pt('보유 배지 숨기기') }}</label>
      </PngExport></div>
    </div>
  </section>
  <DeckAnalysis :deck="deck"/>
</template>
<style scoped>
.recipe-tools{display:flex;align-items:end;justify-content:space-between;flex-wrap:wrap;gap:8px}.recipe-search{min-width:0;flex:1 1 180px}.recipe-tools .recipe-search{margin:0}.recipe-display,.recipe-export-buttons{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.recipe-switch{display:flex;border:1px solid var(--bd);border-radius:8px;padding:2px;background:var(--sf)}.recipe-switch button{border:0;background:transparent;color:var(--tx);padding:4px 10px;font-size:.86rem;min-height:40px}.recipe-switch button[aria-pressed=true]{background:var(--ac);color:var(--sf);border-radius:6px}
.recipe-section h4{display:flex;align-items:baseline;gap:6px}.recipe-section h4 span{color:var(--mu);font-size:.85rem;font-weight:500}.recipe-counts{display:flex;flex-wrap:wrap;gap:3px 12px;color:var(--mu);font-size:.78rem;margin:1px 0 8px}.lib-recipe .recipe-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,86px),1fr));gap:10px}.lib-recipe .recipe-tiles li{padding:0;border:0;display:block;min-width:0}.recipe-tiles a{text-decoration:none;color:var(--tx);display:block}.recipe-tiles strong,.recipe-tiles small{display:block;line-height:1.25;font-size:.73rem;overflow-wrap:anywhere}.recipe-tiles strong{margin-top:3px}.recipe-tiles a:hover strong{text-decoration:underline}.recipe-art{display:grid;place-items:center;width:100%;aspect-ratio:300/438;background:var(--sf);border:1px solid var(--bd);border-radius:4px;overflow:hidden}.recipe-art :deep(.lib-thumbnail){display:block;width:100%;height:100%;background-size:400% 300%;object-fit:contain}.recipe-more{margin-top:9px}.recipe-export{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px}.recipe-export-buttons{margin-left:auto}.recipe-display .text-button{min-height:44px}
</style>
<style scoped>
.recipe-tiles a :deep(.lib-thumbnail){width:100%;aspect-ratio:300/438;object-fit:contain;display:block;border:1px solid var(--bd);border-radius:4px}
.lib-recipe .recipe-tiles{grid-template-columns:repeat(10,minmax(0,1fr));gap:3px}.recipe-tiles a{position:relative}.recipe-tiles a>strong,.recipe-tiles a>small,.recipe-tiles a :deep(.card-text-credit){display:none}.recipe-art small{font-size:clamp(6px,1.5vw,10px)}
.recipe-tags{position:absolute;inset:1px 1px auto;display:flex;justify-content:flex-end;gap:1px}.recipe-tags small{display:block;font-size:.6rem;padding:0 2px;background:var(--tx);color:var(--sf);border-radius:2px}
.recipe-title{position:absolute;clip-path:inset(50%);width:1px;height:1px;overflow:hidden}
.recipe-tiles.with-details a>strong,.recipe-tiles.with-details a>small,.recipe-tiles.with-details a :deep(.card-text-credit){display:block;font-size:clamp(.58rem,1.8vw,.73rem)}
.recipe-quantity{text-align:end;font-variant-numeric:tabular-nums;margin-inline-start:auto}.recipe-quantity small{display:block;color:var(--mu);font-size:.76rem}.recipe-index{color:var(--mu);font-variant-numeric:tabular-nums}
</style>
