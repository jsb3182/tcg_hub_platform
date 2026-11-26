<script setup>
import { computed, ref, watch } from 'vue'
import { t } from '../i18n'
import { curve, drawableEntries, openingHand, openingSizes } from '../deckSample'
import LibraryThumbnail from './LibraryThumbnail.vue'

const props = defineProps({deck:{type:Object,required:true}})
const entries = computed(()=>drawableEntries(props.deck.entries))
const total = computed(()=>entries.value.reduce((count,entry)=>count+entry.quantity,0))
const distribution = computed(()=>curve(entries.value))
const peak = computed(()=>Math.max(1,...distribution.value.bins.map(([,count])=>count)))
const measure = computed(()=>t(({YUGIOH:'몬스터 레벨',POKEMON:'최소 기술 에너지',RIFTBOUND:'에너지 비용'})[props.deck.gameCode] || '카드 비용'))
const size = ref(5)
const hand = ref([])
const validSize = computed(()=>Number.isInteger(size.value) && size.value>=1 && size.value<=10)
watch(()=>props.deck.gameCode, game=>{size.value=openingSizes[game] || 5},{immediate:true})
watch([entries,size],()=>{hand.value=[]})
function draw() { hand.value=openingHand(entries.value,size.value) }
</script>

<template>
  <div class="deck-analysis">
    <section class="lib-panel curve-panel">
      <h2>{{ $t('덱 커브') }}</h2>
      <p class="measure">{{ measure }} · {{ $t('메인') }} {{ total }}{{ $t('장') }}</p>
      <ul v-if="distribution.bins.length" class="curve-list" :aria-label="measure">
        <li v-for="[value,count] in distribution.bins" :key="value">
          <span>{{ value }}</span><span class="curve-track" aria-hidden="true"><i :style="{width:100 * count / peak + '%'}"></i></span><span>{{ count }}{{ $t('장') }}</span>
        </li>
      </ul>
      <p v-if="distribution.unknown" class="measure">{{ $t('수치 없음') }} · {{ distribution.unknown }}{{ $t('장') }}</p>
      <p v-if="!total" class="measure">{{ $t('메인 덱에 카드가 없습니다.') }}</p>
    </section>
    <section class="lib-panel opening-panel">
      <h2>{{ $t('시작 패 시뮬레이션') }}</h2>
      <form @submit.prevent="draw">
        <label>{{ $t('뽑을 장수') }}<input v-model.number="size" type="number" min="1" max="10" required inputmode="numeric"></label>
        <button class="secondary" :disabled="!validSize || !total">{{ $t('섞어 뽑기') }}</button>
      </form>
      <p v-if="total && validSize && size>total" class="measure">{{ $t('메인 덱에 있는 카드만 뽑습니다.') }}</p>
      <p v-if="!total" class="measure">{{ $t('메인 덱에 카드가 없습니다.') }}</p>
      <p v-if="hand.length" role="status" class="measure">{{ $t('손패') }} {{ hand.length }}{{ $t('장') }} · {{ $t('남은 덱') }} {{ total-hand.length }}{{ $t('장') }}</p>
      <ol v-if="hand.length" class="sample-hand">
        <li v-for="(entry,i) in hand" :key="entry.cardId+'-'+i">
          <LibraryThumbnail :image="entry.image" :src="entry.image ? undefined : entry.imageUrl"/>
          <span>{{ entry.name }} <small>{{ entry.number }}</small></span>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.deck-analysis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));gap:0 1rem;align-items:start}
.deck-analysis h2{margin:0}.measure{color:var(--mu);font-size:.9rem;margin:.4rem 0}
.curve-list,.sample-hand{list-style:none;padding:0;margin:.8rem 0 0}
.curve-list li{display:grid;grid-template-columns:minmax(2ch,auto) 1fr auto;align-items:center;gap:.75rem;font-variant-numeric:tabular-nums}
.curve-track{display:block;background:var(--bg);height:.5rem;border-radius:2px;overflow:hidden}
.curve-track i{display:block;background:var(--ac);height:100%}
.opening-panel form{display:flex;align-items:end;flex-wrap:wrap;gap:.65rem;margin:.6rem 0}
.opening-panel form label{margin:0}.opening-panel input{width:6rem;min-height:44px}
.opening-panel button{min-height:44px}.sample-hand li{display:flex;align-items:center;gap:.6rem;overflow-wrap:anywhere;border-top:1px solid var(--bd);padding:.45rem 0}
.sample-hand .lib-thumbnail{flex-basis:30px}.sample-hand small{display:block}
</style>
