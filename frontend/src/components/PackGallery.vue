<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import LibraryThumbnail from './LibraryThumbnail.vue'
import ArtworkCredit from './ArtworkCredit.vue'
import CardTextCredit from './CardTextCredit.vue'
import PngExport from './PngExport.vue'
import { countLabel, facetLabel, facetValues, pt } from '../pack'
import { pngSnapshot } from '../pngSnapshot'

const props=defineProps({pack:{type:Object,required:true},cards:{type:Array,required:true},loading:Boolean,hasMore:Boolean,error:String})
const emit=defineEmits(['pick','load'])
const dialog=ref(), tiles=ref(), opener=ref(), page=ref(0)
const fields={inclusion:'수록 구분',type:'카드 종류',rarity:'레어도'}
const chosen=reactive({inclusion:[],type:[],rarity:[]})
const options=computed(()=>Object.fromEntries(Object.keys(fields).map(key=>[
  key,[...new Set(props.cards.flatMap(card=>facetValues(card,key)))],
])))
const filtered=computed(()=>props.cards.filter(card=>Object.keys(fields).every(key=>
  !chosen[key].length || facetValues(card,key).some(value=>chosen[key].includes(value)))))
const hasFilters=computed(()=>Object.values(chosen).some(values=>values.length))
const pageSize=60
const pages=computed(()=>Math.ceil(filtered.value.length/pageSize))
const shown=computed(()=>filtered.value.slice(page.value*pageSize,(page.value+1)*pageSize))
watch(chosen,()=>{page.value=0})
function reset(){for(const key of Object.keys(fields)) chosen[key]=[]}
let previousOverflow
function open(){
  dialog.value.showModal()
  previousOverflow=document.body.style.overflow
  document.body.style.overflow='hidden'
  if(props.hasMore) emit('load')
}
function restoreScroll(){
  if(previousOverflow!==undefined){document.body.style.overflow=previousOverflow;previousOverflow=undefined}
}
function close(){dialog.value.close();restoreScroll()}
function pick(id){close();emit('pick',id)}
async function exportPage(){return pngSnapshot(tiles.value,props.pack.name,
  [props.pack.code,countLabel(filtered.value.length),pages.value>1?(page.value+1)+' / '+pages.value:''].filter(Boolean).join(' · '),720)}
onBeforeUnmount(restoreScroll)
</script>
<template>
  <button ref="opener" type="button" class="secondary gallery-trigger" @click="open" :disabled="!cards.length" aria-haspopup="dialog">
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="11" y="2" width="5" height="5" rx="1"/><rect x="2" y="11" width="5" height="5" rx="1"/><rect x="11" y="11" width="5" height="5" rx="1"/></svg>{{ pt('카드 배열') }}
  </button>
  <dialog ref="dialog" class="pack-gallery" aria-labelledby="pack-gallery-title" @close="restoreScroll" @click="e=>{if(e.target===dialog)close()}">
    <div class="gallery-frame">
      <header class="gallery-top"><div><small>{{ pack.name }}</small><h2 id="pack-gallery-title">{{ pt('카드 배열') }}</h2></div>
        <button class="secondary" type="button" @click="close">{{ pt('닫기') }}</button>
      </header>
      <div class="gallery-body">
        <section class="gallery-filters" :aria-label="pt('배열 필터')">
          <fieldset v-for="(label,key) in fields" :key="key">
            <legend>{{ pt(label) }}</legend><div class="gallery-options">
              <button class="facet-all" type="button" :aria-pressed="!chosen[key].length" @click="chosen[key]=[]">{{ pt('전체') }}</button>
              <label v-for="value in options[key]" :key="value" :class="{active:chosen[key].includes(value)}">
                <input type="checkbox" v-model="chosen[key]" :value="value"><span>{{ facetLabel(key,value) }}</span>
              </label>
            </div>
          </fieldset>
        </section>
        <div class="gallery-result"><strong role="status">{{ countLabel(filtered.length) }}</strong>
          <button v-if="hasFilters" class="text-button" type="button" @click="reset">{{ pt('필터 지우기') }}</button>
        </div>
        <p v-if="loading" class="muted" role="status">{{ pt('카드 불러오는 중…') }}</p>
        <p v-if="error" role="alert" class="inline-error">{{ error }} <button type="button" class="text-button" @click="emit('load')">{{ pt('다시 시도') }}</button></p>
        <p v-if="!shown.length && !loading" class="state">{{ pt('검색 결과가 없습니다.') }}</p>
        <div v-else ref="tiles" class="pack-tiles">
          <button type="button" class="pack-tile" v-for="card in shown" :key="card.id" @click="pick(card.id)">
            <LibraryThumbnail :image="card.image" :src="card.imageUrl" :language="card.imageLanguage" :printing="card" v-slot="{art}">
              <span v-if="!art" class="tile-image">{{ pt('이미지 없음') }}</span>
              <small v-if="card.number">{{ card.number }}</small><strong :lang="card.language || ''">{{ card.name }}</strong>
              <small v-if="art?.reference"><ArtworkCredit :language="art.language" :printing="card" disable-link/></small>
              <CardTextCredit :card="card"/>
            </LibraryThumbnail>
          </button>
        </div>
      </div>
      <footer class="gallery-bottom">
        <nav v-if="pages>1" :aria-label="pt('페이지')"><button type="button" class="secondary" :disabled="page===0" @click="page--">{{ pt('이전') }}</button><span>{{ page+1 }} / {{ pages }}</span><button type="button" class="secondary" :disabled="page+1>=pages" @click="page++">{{ pt('다음') }}</button></nav>
        <PngExport v-if="shown.length" :render="exportPage" :name="pack.code+'-'+(page+1)" :label="pt(pages>1?'이 페이지 PNG 저장':'배열 PNG 저장')"/>
      </footer>
    </div>
  </dialog>
</template>
<style scoped>
.gallery-trigger{display:inline-flex;gap:7px;align-items:center;justify-content:center;min-height:44px;white-space:nowrap}
.pack-gallery{padding:0;width:min(880px,calc(100% - 32px));max-height:88vh;border:1px solid var(--bd);border-radius:16px;background:var(--sf);color:var(--tx);overflow:hidden}.pack-gallery::backdrop{background:rgb(0 0 0 / .56)}
.gallery-frame{display:flex;flex-direction:column;max-height:88vh}.gallery-top,.gallery-bottom,.gallery-result{display:flex;gap:12px;align-items:center;justify-content:space-between}.gallery-top{padding:15px 20px;border-bottom:1px solid var(--bd)}.gallery-top h2{font-size:1.25rem;margin:0}.gallery-top small{color:var(--mu);overflow-wrap:anywhere}.gallery-top button{flex:none;min-height:44px}
.gallery-body{padding:16px 20px;overflow-y:auto;overscroll-behavior:contain}.gallery-filters{display:grid;gap:9px}.gallery-filters fieldset{padding:0;margin:0;border:0;min-width:0}.gallery-filters legend{padding:0;font-size:.8rem;font-weight:650;color:var(--mu)}.gallery-options{display:flex;gap:5px;flex-wrap:wrap;margin-top:2px}
.gallery-options label{position:relative;cursor:pointer}.gallery-options input{position:absolute;opacity:0;width:1px;height:1px;min-height:0;margin:0}.gallery-options span{min-height:34px;display:flex;align-items:center;padding:3px 10px;border:1px solid var(--bd);border-radius:6px;font-size:.85rem;font-weight:500}.gallery-options .active span{background:var(--ac);color:var(--sf);border-color:var(--ac)}.gallery-options input:focus-visible+span{outline:2px solid var(--ac);outline-offset:2px}
.facet-all{padding:3px 10px;min-height:34px;border:1px solid var(--bd);border-radius:6px;background:var(--sf);color:var(--tx);font-size:.85rem}.facet-all[aria-pressed=true]{background:var(--tx);color:var(--sf);border-color:var(--tx)}
.gallery-result{border-top:1px solid var(--bd);margin:14px 0 10px;padding-top:12px}.gallery-result strong{font-size:.91rem;font-variant-numeric:tabular-nums}
.pack-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,105px),1fr));gap:14px 10px}.pack-tile{display:block;padding:0;border:0;background:transparent;text-align:start;min-width:0;color:var(--tx)}.pack-tile:hover strong{text-decoration:underline;color:var(--ac)}.pack-tile strong,.pack-tile small{display:block;overflow-wrap:anywhere;line-height:1.32}.pack-tile strong{font-size:.84rem;font-weight:650}.pack-tile small{margin:5px 0 3px;color:var(--mu);font-size:.7rem}
.tile-image{display:grid;width:100%;aspect-ratio:300/438;place-items:center;overflow:hidden;background:var(--bg);font-size:.7rem;color:var(--mu);border:1px solid var(--bd);border-radius:5px}.tile-image :deep(.lib-thumbnail){height:100%;width:100%;display:block;object-fit:contain;background-size:400% 300%;background-repeat:no-repeat}
.gallery-bottom{flex-wrap:wrap;justify-content:flex-end;padding:10px 20px;border-top:1px solid var(--bd)}.gallery-bottom nav{display:flex;gap:8px;align-items:center;margin-right:auto}.gallery-bottom span{font-size:.8rem}
@media(max-width:560px){.pack-gallery{width:100%;max-width:100%;max-height:94vh;margin:auto 0 0;border-radius:16px 16px 0 0}.gallery-frame{max-height:94vh}.gallery-top,.gallery-body,.gallery-bottom{padding-inline:14px}.gallery-bottom{padding-bottom:max(10px,env(safe-area-inset-bottom))}.pack-tiles{grid-template-columns:repeat(3,minmax(0,1fr))}.gallery-bottom .secondary{padding-inline:9px}.gallery-options span{min-height:40px}}
</style>
<style scoped>.pack-tile :deep(.lib-thumbnail){display:block;width:100%;aspect-ratio:300/438;object-fit:contain}</style>
