<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LibraryThumbnail from '../components/LibraryThumbnail.vue'
import { request, artworkUrl } from '../api'
import { useSession } from '../stores/session'
import { newRound, playGames, playText, practiceLanguage, practiceOpening,
  rememberPracticeLanguage, rememberPracticeOpening, validOpeningSize } from '../play'

const route = useRoute()
const router = useRouter()
const session = useSession()
const game = computed(() => typeof route.query.game === 'string' && Object.hasOwn(playGames, route.query.game) ? route.query.game : 'YUGIOH')
const lang = computed(() => practiceLanguage(route.query.lang))
const t = computed(() => playText[lang.value])
const deckId = computed(() => typeof route.query.deck === 'string' && /^[1-9]\d*$/.test(route.query.deck) ? route.query.deck : '')
const query = ref('')
const search = ref('')
const retry = ref(0)
const deckRetry = ref(0)
const labelsRetry = ref(0)
const hits = ref([])
const busy = ref(false)
const error = ref(false)
const deckError = ref(false)
const deckBusy = ref(false)
const labelError = ref(false)
const deckName = ref('')
const cards = ref([])
const labels = ref({})
const round = ref(null)
const opening = ref(practiceOpening(game.value))
const total = computed(() => cards.value.reduce((count, card) => count + card.quantity, 0))
const ids = computed(() => cards.value.map(card => card.id).join(','))
const identity = computed(() => session.account?.email || '')
const validOpening = computed(() => validOpeningSize(opening.value))
const zones = ['hand', 'table', 'discard']
const stock=ref(0), spent=ref(0), amount=ref(1), attached=ref([]), exchange=ref([])
const remainingDon=computed(()=>10-stock.value-spent.value-attached.value.reduce((sum,n)=>sum+n,0))
function resetResources(){
  stock.value=game.value==='YUGIOH'?8000:0
  spent.value=0;amount.value=1;attached.value=[];exchange.value=[]
}
function allowed(delta){
  const n=amount.value
  return Number.isInteger(n)&&n>=1&&n<=99999&&(delta<0?n<=stock.value:game.value!=='ONEPIECE'||n<=remainingDon.value)
}
function pay(delta){
  if(!allowed(delta))return
  stock.value+=delta*amount.value
  if(delta<0&&game.value==='ONEPIECE')spent.value+=amount.value
}
function attach(i){if(stock.value){stock.value--;attached.value[i]++}}
function redraw(){
  const {hand,pile}=round.value
  if(!exchange.value.length||exchange.value.length>pile.length)return
  const old=exchange.value.map(i=>hand[i])
  for(const i of exchange.value)hand[i]=pile.shift()
  pile.push(...old)
  for(let i=pile.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[pile[i],pile[j]]=[pile[j],pile[i]]}
  exchange.value=[]
}
watch(() => route.query.lang, rememberPracticeLanguage, {immediate:true})
watch(game, code => { opening.value = practiceOpening(code) }, {flush:'sync'})
watch(opening, size => rememberPracticeOpening(game.value, size), {flush:'sync'})

function selectGame(code) {
  if (game.value !== code) router.push({ name: 'play', query: { game: code, lang: lang.value } })
}
function params() { return new URLSearchParams({ game: game.value, lang: lang.value }) }
watch([game, lang, search, retry], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  const p = params()
  p.set('q', search.value)
  error.value = false
  busy.value = true
  hits.value = []
  try { const result = await request('/play/cards?' + p, { signal: controller.signal })
    if (!controller.signal.aborted) hits.value = result
  } catch { if (!controller.signal.aborted) error.value = true }
  finally { if (!controller.signal.aborted) busy.value = false }
}, { immediate: true })

watch([game, deckId, identity, deckRetry], async ([currentGame, id, account], previous, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  if (!previous || previous[0] !== currentGame || previous[1] !== id || id && previous[2] !== account) {
    cards.value = []
    round.value = null
    deckName.value = ''
    search.value = query.value = ''
  }
  deckBusy.value = false
  deckError.value = false
  if (!id || !account) return
  try {
    deckBusy.value = true
    const deck = await session.authenticatedRequest('/me/decks/' + id, { signal: controller.signal })
    if (controller.signal.aborted) return
    if (deck.gameCode !== currentGame) throw new Error()
    const entries = deck.entries.filter(card => card.section === 'MAIN')
    if (entries.reduce((n, e) => n + e.quantity, 0) > 150) throw new Error()
    cards.value = entries.map(card => ({ id: card.cardId, name: card.name, quantity: card.quantity }))
    deckName.value = deck.name
  } catch { if (!controller.signal.aborted) deckError.value = true }
  finally { if (!controller.signal.aborted) deckBusy.value = false }
}, { immediate: true })

watch([game, lang, ids, labelsRetry], async (_, __, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  labels.value = {}
  labelError.value = false
  if (!ids.value) return
  const p = params()
  p.set('ids', ids.value)
  try {
    const result = await request('/play/cards?' + p, { signal: controller.signal })
    if (!controller.signal.aborted) labels.value = Object.fromEntries(result.map(card => [card.id, card]))
  } catch { if (!controller.signal.aborted) labelError.value = true }
}, { immediate: true })

function label(id) {
  return labels.value[id] || cards.value.find(card => card.id === id)
}
function changeQuantity(card, amount) {
  const entry = cards.value.find(item => item.id === card.id)
  if (amount > 0 && total.value >= 150) return
  if (entry) {
    entry.quantity += amount
    if (entry.quantity === 0) cards.value = cards.value.filter(item => item.id !== card.id)
  } else if (amount > 0) cards.value.push({ ...card, quantity: amount })
}
function start() {
  if (total.value && validOpening.value) { round.value = newRound(cards.value, opening.value); resetResources() }
}
function move(from, index, to) {
  if(index<0||index>=round.value[from].length)return
  if(from==='table'){const [n]=attached.value.splice(index,1);if(game.value==='ONEPIECE')spent.value+=n||0}
  if(to==='table')attached.value.push(0)
  exchange.value=[]
  round.value[to].push(...round.value[from].splice(index,1))
}
</script>

<template>
  <section class="play-page" :lang="lang">
    <header class="page-heading play-heading">
      <h1>{{ t.title }}</h1>

    </header>
    <nav class="game-tabs" :aria-label="t.game">
      <button v-for="(info, code) in playGames" :key="code" :aria-pressed="game === code"
        :disabled="!!round && game !== code" @click="selectGame(code)">{{ info.name[lang] }}</button>
    </nav>
    <section v-if="playGames[game].app" class="panel official">
      <div><h2>{{ playGames[game].app }}</h2><p>{{ t.about }}</p></div>
      <a :href="playGames[game].urls[lang]" target="_blank" rel="noopener noreferrer">{{ t.official }} ↗</a>
      <a :href="'https://play.google.com/store/apps/details?id='+playGames[game].androidPackage+'&hl='+lang" target="_blank" rel="noopener noreferrer">Google Play ↗</a>
    </section>
    <header class="section-heading"><h2>{{ t.practice }}</h2><RouterLink :to="{name:'decks',query:{lang}}">{{ t.choose }}</RouterLink></header>
    <p v-if="deckBusy">{{ t.loading }}</p>
    <p v-if="deckId && session.ready && !session.account"><RouterLink :to="{name:'login',query:{next:route.fullPath}}">{{ t.login }}</RouterLink></p>
    <p v-if="deckError" role="alert">{{ t.deckError }} <button @click="deckRetry++">{{ t.retry }}</button></p>
    <p v-if="labelError" role="alert">{{ t.fail }} <button @click="labelsRetry++">{{ t.retry }}</button></p>
    <p v-if="deckName">{{ t.main }} · {{ deckName }}</p>
    <div v-if="!round" class="practice-setup">
      <section class="panel">
        <form class="play-search" @submit.prevent="search=query.trim(); if (error) retry++">
          <label>{{ t.search }}<input v-model="query" type="search" maxlength="100" /></label>
          <button class="secondary">{{ t.find }}</button>
        </form>
        <p v-if="busy" role="status">{{ t.loading }}</p>
        <p v-else-if="error" role="alert">{{ t.fail }} <button @click="retry++">{{ t.retry }}</button></p>
        <p v-else-if="!hits.length">{{ t.noHits }}</p>
        <ul v-else class="play-hits">
          <li v-for="card in hits" :key="card.id"><div><strong :lang="card.language">{{ card.name }}</strong>
            <small>{{ card.number }} <span v-if="card.language !== lang">· {{ t.fallback }} ({{ card.language }})</span></small></div>
            <button class="secondary" :disabled="total >= 150" :aria-label="t.add + ' ' + card.name" @click="changeQuantity(card,1)">{{ t.add }}</button>
          </li>
        </ul>
      </section>
      <section class="panel">
        <h3>{{ t.selection }} · {{ total }}</h3><p v-if="!total">{{ t.empty }}</p>
        <ul class="play-list"><li v-for="card in cards" :key="card.id">
          <span :lang="label(card.id)?.language">{{ label(card.id)?.name }} × {{ card.quantity }}</span>
          <button class="secondary" :aria-label="t.remove+' '+label(card.id)?.name" @click="changeQuantity(card,-1)">−</button>
        </li></ul>
        <p v-if="total >= 150">{{ t.limit }}</p>
        <label>{{ t.opening }}<input v-model.number="opening" type="number" min="1" max="10" /></label>
        <button class="primary wide" :disabled="!total || !validOpening || deckBusy" @click="start">{{ t.start }}</button>
      </section>
    </div>
    <template v-else>
      <div class="play-controls">
        <strong aria-live="polite">{{ t.pile }} · {{ round.pile.length }}</strong>
        <button class="primary" :disabled="!round.pile.length" @click="move('pile',0,'hand')">{{ t.draw }}</button>
        <button class="secondary" @click="start">{{ t.reset }}</button>
        <button class="secondary" @click="round=null">{{ t.end }}</button>
      </div>
      <section class="panel resource-controls"><h3>{{ game==='ONEPIECE'?'DON!!':game==='POKEMON'?$t('에너지'):$t('라이프 포인트') }} · {{ stock }}</h3>
        <span v-if="game==='ONEPIECE'">{{ $t('남은 DON!!') }} {{ remainingDon }} · {{ $t('레스트') }} {{ spent }}</span>
        <label>{{ $t('수량') }}<input v-model.number="amount" min="1" max="99999" type="number"></label>
        <button class="secondary" :disabled="!allowed(1)" @click="pay(1)">{{ $t('추가') }}</button><button class="secondary" :disabled="!allowed(-1)" @click="pay(-1)">{{ $t('코스트 지불') }}</button>
        <button v-if="game==='ONEPIECE'" class="secondary" :disabled="!spent" @click="stock+=spent;spent=0">{{ $t('액티브로 전환') }}</button></section>
      <div class="practice-zones">
        <section v-for="zone in zones" :key="zone" class="panel"><h3>{{ t[zone] }} · {{ round[zone].length }}</h3>
          <p v-if="!round[zone].length">{{ t.empty }}</p>
          <ul class="play-list"><li v-for="(id, i) in round[zone]" :key="id+'-'+i">
            <label v-if="zone==='hand'" class="exchange-card"><input type="checkbox" v-model="exchange" :value="i" :aria-label="$t('교환할 카드')+' '+label(id)?.name"></label>
            <img v-if="artworkUrl(label(id)?.imageUrl)" class="play-art" :src="artworkUrl(label(id).imageUrl)" alt="" loading="lazy" referrerpolicy="no-referrer">
            <LibraryThumbnail v-else-if="label(id)?.image" :image="label(id).image"/>
            <span><strong :lang="label(id)?.language">{{ label(id)?.name }}</strong>
              <small v-if="label(id)?.language && label(id).language !== lang"> · {{ t.fallback }} ({{ label(id).language }})</small></span>
            <details v-if="label(id)?.effect"><summary>{{ $t('효과') }}</summary><p :lang="label(id).effectLanguage">{{ label(id).effect }}</p></details>
            <small v-if="zone==='table' && attached[i]">{{ game==='ONEPIECE'?'DON!!':$t('에너지') }} × {{ attached[i] }}</small>
            <button v-if="zone==='table' && game!=='YUGIOH'" class="secondary" :disabled="!stock" @click="attach(i)">{{ $t('부착') }}</button>
            <div><button v-if="zone === 'hand'" class="secondary" @click="move(zone,i,'table')">{{ t.place }}</button>
              <button v-if="zone !== 'discard'" class="secondary" @click="move(zone,i,'discard')">{{ t.drop }}</button>
              <button v-if="zone !== 'hand'" class="secondary" @click="move(zone,i,'hand')">{{ t.back }}</button></div>
          </li></ul>
          <button v-if="zone==='hand'" class="secondary" :disabled="!exchange.length||exchange.length>round.pile.length" @click="redraw">{{ $t('선택한 패 교환') }} ({{ exchange.length }})</button>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.play-page { padding-bottom: 2rem; }
.play-heading,.official,.play-controls,.play-search,.play-list li,.play-hits li { display:flex; align-items:center; gap:.65rem; justify-content:space-between; }
.official { margin:1rem 0; flex-wrap:wrap; }
.official h2,.official p,.play-page h3 { margin:.3rem 0; }
.official p,.play-hits small { color:var(--mu); }
.practice-setup,.practice-zones { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr)); gap:1rem; align-items:start; }
.play-hits,.play-list { list-style:none; margin:.5rem 0; padding:0; }
.play-hits { max-height:20rem; overflow:auto; }
.play-hits small { display:block; }
.play-hits li,.play-list li { padding:.45rem 0; border-bottom:1px solid var(--bd); overflow-wrap:anywhere; }
.play-hits button,.play-list button { flex-shrink:0; }
.play-page label { display:block; }
.play-page input { display:block; width:100%; margin:.3rem 0; }
.play-page select,.play-page input { padding:.55rem; }
.play-controls { flex-wrap:wrap; justify-content:flex-start; margin:1rem 0; }
.play-list li div { display:flex; gap:.3rem; flex-wrap:wrap; }
.play-search { align-items:end; }
.play-search label { flex:1; }
.resource-controls {display:flex;gap:.55rem;align-items:center;flex-wrap:wrap;margin:1rem 0}
.resource-controls input {width:5rem}.play-art {width:40px;height:56px;object-fit:contain}
.practice-zones li {flex-wrap:wrap}.play-page .exchange-card input {width:20px;height:20px}.practice-zones details p {white-space:pre-line}
</style>
