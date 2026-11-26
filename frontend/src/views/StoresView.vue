<script setup>
import { t as uiText, gameCodes, gameName, locale } from '../i18n'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {loadKakao,kakaoStores} from '../kakao'
import {dateTime} from '../presentation'
import Map from 'ol/Map.js'
import View from 'ol/View.js'
import TileLayer from 'ol/layer/Tile.js'
import VectorLayer from 'ol/layer/Vector.js'
import OSM from 'ol/source/OSM.js'
import VectorSource from 'ol/source/Vector.js'
import Feature from 'ol/Feature.js'
import Point from 'ol/geom/Point.js'
import { fromLonLat, toLonLat } from 'ol/proj.js'
import { Circle as CircleStyle, Fill, Stroke, Style } from 'ol/style.js'
import { defaults as controls } from 'ol/control/defaults.js'
import 'ol/ol.css'
import '../styles/stores.css'
import { request, sourceLink } from '../api'
import { useSession } from '../stores/session'

const session = useSession()
const names=computed(()=>Object.fromEntries(gameCodes.map(g=>[g,gameName(g)])))
const mapElement = ref(null), shops = ref([]), total = ref(0), selected = ref(null)
const draft = ref(''), q = ref(''), game = ref(''), radius = ref(10), center = ref(null), page = ref(0)
const busy = ref(true), error = ref(''), locationNote = ref(''), locating = ref(false), tileError = ref(false)
const favorites = ref(new Set()), favoritesOnly = ref(false), saving = ref(new Set()), favoriteError = ref('')
const refresh = ref(0), size = 75
const active = computed(() => shops.value.find(s => s.id === selected.value))
const pages = computed(() => Math.ceil(total.value / size))
const vector = new VectorSource()
const makeMarker = (fill, radius) => new Style({ image: new CircleStyle({radius, fill:new Fill({color:fill}), stroke:new Stroke({color:'#fff',width:2})}) })
const marker = makeMarker('#12635c',7), chosen = makeMarker('#b34715',10)
let kakaoMap, map, disposed = false, generation = 0

onMounted(async () => {
  try{
    const config=await request('/config')
    if(config.kakaoMapKey){
      const api=await loadKakao(config.kakaoMapKey)
      if(disposed)return
      kakaoMap=kakaoStores(api,mapElement.value,id=>choose(id,false))
      draw();return
    }
  }catch{ /* The local store index remains available on OpenStreetMap. */ }
  if(disposed)return
  const base = new OSM({ url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attributionsCollapsible:false })
  base.on('tileloaderror', () => { tileError.value = true })
  map = new Map({ target:mapElement.value, controls:controls({attributionOptions:{collapsible:false}}),
    layers:[new TileLayer({source:base}),new VectorLayer({source:vector,style:f => f.getId()===selected.value ? chosen : marker})],
    view:new View({center:fromLonLat([127.85,36.2]), zoom:6.5, minZoom:4, maxZoom:19}) })
  map.on('singleclick', event => {
    const match = map.forEachFeatureAtPixel(event.pixel, f => f, {hitTolerance:9})
    if (match) choose(match.getId(), false)
  })
  draw()
  session.initialize()
})
onBeforeUnmount(() => { disposed=true;kakaoMap?.dispose(); map?.setTarget(undefined) })
function draw() {
  if(kakaoMap){kakaoMap.draw(shops.value,center.value);return}
  vector.clear()
  for (const s of shops.value) {
    const feature = new Feature(new Point(fromLonLat([s.lon,s.lat])))
    feature.setId(s.id)
    vector.addFeature(feature)
  }
  if (!map) return
  if (shops.value.length) {
    map.getView().fit(vector.getExtent(), {padding:[35,32,35,32],maxZoom:14,duration:0})
  } else if (center.value) {
    map.getView().setCenter(fromLonLat(center.value))
    map.getView().setZoom(11)
  }
}
function choose(id, move=true) {
  selected.value=id
  if(kakaoMap){if(move&&active.value)kakaoMap.select(active.value);return}
  vector.changed()
  if (move && map && active.value) {
    map.getView().animate({center:fromLonLat([active.value.lon,active.value.lat]),zoom:15,duration:250})
  }
}
function directions(s) { return 'https://map.kakao.com/link/to/'+encodeURIComponent(s.name)+','+s.lat+','+s.lon }
function applySearch() { page.value=0; q.value=draft.value.trim() }
function searchHere() {
  if (!map && !kakaoMap) return
  page.value=0; center.value=kakaoMap?kakaoMap.center():toLonLat(map.getView().getCenter()); locationNote.value=uiText("지도 중심 기준")
}
function resetCenter() { page.value=0; center.value=null; locationNote.value='' }
function nearMe() {
  if (!navigator.geolocation) { locationNote.value=uiText("이 브라우저에서 위치를 사용할 수 없습니다."); return }
  locating.value=true
  navigator.geolocation.getCurrentPosition(pos => {
    if (disposed) return
    locating.value=false; page.value=0; center.value=[pos.coords.longitude,pos.coords.latitude]; locationNote.value=uiText("내 위치 기준")
  }, () => {
    if (!disposed) { locating.value=false; locationNote.value=uiText("위치를 확인할 수 없습니다. 지도 중심으로 검색할 수 있습니다.") }
  }, {timeout:10000, maximumAge:60000})
}
watch([q,game,radius,center,page,refresh,favoritesOnly], async (_,__,cleanup) => {
  const controller=new AbortController()
  cleanup(() => controller.abort())
  busy.value=true; error.value=''
  const params = new URLSearchParams({ q:q.value, game:game.value, page:String(page.value), size:String(size) })
  if (center.value) {
    params.set('lat',center.value[1].toFixed(5)); params.set('lon',center.value[0].toFixed(5)); params.set('radiusKm',String(radius.value))
  }
  try {
    const result=favoritesOnly.value
      ? await session.authenticatedRequest('/me/favorites/stores/search?'+params,{signal:controller.signal})
      : await request('/stores?'+params,{signal:controller.signal})
    if (controller.signal.aborted) return
    shops.value=result.items; total.value=result.total; selected.value=null; draw()
  } catch (e) {
    if (!controller.signal.aborted) { error.value=e.message; shops.value=[]; total.value=0; selected.value=null; draw() }
  } finally { if (!controller.signal.aborted) busy.value=false }
}, {immediate:true})
watch(() => session.account?.email, async (email,_,cleanup) => {
  generation++
  favoritesOnly.value=false
  favorites.value=new Set(); saving.value=new Set(); favoriteError.value=''
  if (!email) return
  const controller=new AbortController()
  cleanup(() => controller.abort())
  try {
    const result=await session.authenticatedRequest('/me/favorites/stores',{signal:controller.signal})
    if (!controller.signal.aborted) favorites.value=new Set(result)
  } catch (e) { if (!controller.signal.aborted) favoriteError.value=e.message }
}, {immediate:true})
async function toggle(id) {
  if (saving.value.has(id)) return
  const current=generation, was=favorites.value.has(id)
  saving.value.add(id); favoriteError.value=''
  try {
    await session.authenticatedRequest('/me/favorites/stores/'+id,{method:was?'DELETE':'PUT'})
    if (current===generation) {
      if (was) favorites.value.delete(id); else favorites.value.add(id)
      if (favoritesOnly.value) { page.value=0; refresh.value++ }
    }
  } catch(e) { if (current===generation) favoriteError.value=e.message }
  finally { if (current===generation) saving.value.delete(id) }
}
</script>

<template>
  <header class="page-heading"><h1>{{ $t("매장 지도") }}</h1></header>
  <form class="store-search" @submit.prevent="applySearch">
    <label>{{ $t("매장명·지역") }}<input v-model="draft" maxlength="100" :placeholder="$t('매장명 또는 도로명')" type="search"></label>
    <label>{{ $t("취급 게임") }}<select v-model="game" @change="page=0"><option value="">{{ $t("전체 게임") }}</option>
      <option v-for="(name,code) in names" :key="code" :value="code">{{ name }}</option></select></label>
    <button class="secondary" type="submit">{{ $t("검색") }}</button>
  </form>
  <div class="store-controls">
    <button class="secondary" :disabled="locating" @click="nearMe">{{ locating?$t("위치 확인 중"):$t("내 위치 주변") }}</button>
    <button class="secondary" @click="searchHere">{{ $t("지도 중심 주변") }}</button>
    <label>{{ $t("반경") }} <select v-model.number="radius" @change="page=0"><option v-for="n in [2,5,10,25,50,100]" :key="n" :value="n">{{ n }} km</option></select></label>
    <label v-if="session.account"><input type="checkbox" v-model="favoritesOnly" @change="page=0"> {{ $t("즐겨찾기만") }}</label>
    <button v-if="center" class="text-button" @click="resetCenter">{{ $t("전국 보기") }}</button>
    <span role="status">{{ locationNote }}</span>
  </div>
  <div class="store-layout">
    <div class="store-map-panel">
      <div ref="mapElement" tabindex="0" class="store-map" :aria-label="$t('카드 매장 지도')"></div>
      <p v-if="tileError" class="inline-error">{{ $t("배경 지도를 불러오지 못했습니다. 아래 주소 또는 길찾기를 이용해 주세요.") }}</p>
      <section v-if="active" class="store-detail" :aria-label="$t('선택한 매장')" aria-live="polite">
        <h2>{{ active.name }}</h2><p>{{ active.address }}</p><p>{{ $t('공인 매장') }} · {{ $t(active.official==null?'미확인':active.official?'예':'아니요') }}</p>
        <h3>{{ $t('이번 주 대회') }}</h3><ul v-if="active.events?.length"><li v-for="event in active.events" :key="event.id"><time :datetime="event.startsAt">{{dateTime(event.startsAt)}}</time> · {{event.title}} <small>{{gameName(event.gameCode,'')}}</small></li></ul><p v-else>{{ $t('등록된 대회가 없습니다.') }}</p>
        <p>{{ $t("영업시간 ·") }} {{ active.hours?.text || $t("미확인") }}
          <a v-if="sourceLink(active.hours?.url)" :href="sourceLink(active.hours.url)" target="_blank" rel="noopener noreferrer">{{ $t("운영시간 출처") }} {{ active.hours.checked }}</a></p>
        <p>{{ $t("취급 근거 ·") }} <template v-if="active.games.length"><template v-for="g in active.games" :key="g.code">
          <a v-if="sourceLink(g.source)" :href="sourceLink(g.source)" target="_blank" rel="noopener noreferrer">{{ names[g.code] }}</a><span v-else>{{ names[g.code] }}</span> </template></template><span v-else>{{ $t("미확인") }}</span></p>
        <p v-if="active.sourceUrl">{{ $t("주소·좌표 기준") }} {{ active.sourceDate }} · <a :href="active.sourceUrl" target="_blank" rel="noopener noreferrer">{{ $t("소상공인시장진흥공단") }}</a></p>
        <a :href="directions(active)" target="_blank" rel="noopener noreferrer">{{ $t("카카오맵 길찾기 ↗") }}</a>
      </section>
    </div>
    <section class="store-results" :aria-label="$t('매장 검색 결과')" :aria-busy="busy">
      <h2>{{ $t("검색 결과") }} <span>{{ total }}{{ $t("곳") }}</span></h2>
      <p v-if="busy" role="status">{{ $t("매장을 찾고 있습니다.") }}</p>
      <p v-else-if="error" role="alert">{{ error }} <button class="text-button" @click="refresh++">{{ $t("다시 시도") }}</button></p>
      <p v-else-if="!shops.length">{{ $t("해당 조건으로 등록된 매장이 없습니다.") }}</p>
      <p v-if="favoriteError" role="alert">{{ favoriteError }}</p>
      <ul v-if="!busy && shops.length">
        <li v-for="s in shops" :key="s.id" :class="{selected:s.id===selected}">
          <button class="store-select" :aria-pressed="selected===s.id" @click="choose(s.id)"><strong>{{ s.name }}</strong>
            <small v-if="s.distanceKm!=null">{{ s.distanceKm.toFixed(1) }} km</small><span>{{ s.address }}</span>
            <small>{{ s.games.length?s.games.map(g=>names[g.code]).join(' · '):$t("취급 게임 미확인") }}</small></button>
          <button v-if="session.account" class="text-button store-favorite" :disabled="saving.has(s.id)" :aria-pressed="favorites.has(s.id)"
            :aria-label="s.name+$t(' 즐겨찾기')" @click="toggle(s.id)">{{ favorites.has(s.id)?'★':'☆' }}</button>
          <a :href="directions(s)" target="_blank" rel="noopener noreferrer">{{ $t("길찾기 ↗") }}</a>
        </li>
      </ul>
      <nav v-if="!busy && pages>1" :aria-label="$t('매장 목록 페이지')"><button :disabled="page===0" @click="page--">{{ $t("이전") }}</button>
        {{ page+1 }} / {{ pages }} <button :disabled="page+1>=pages" @click="page++">{{ $t("다음") }}</button></nav>
    </section>
  </div>
  <p class="store-coverage">{{ $t("전국 상가업소 분기 자료에서 TCG 전문 상호와 공식 취급 근거를 확인할 수 있는 점포를 표시합니다. 게임 목록과 재고는 매장마다 다릅니다.") }}</p>
</template>
