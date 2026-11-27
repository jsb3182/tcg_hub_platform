<script setup>
import { computed, ref, watch } from 'vue'
import { sourceLink } from '../api'
import { locale } from '../i18n'
import { useSession } from '../stores/session'

const props=defineProps({region:{type:String,default:''},regions:Array,entries:{type:Array,default:()=>[]},savedReport:Object,editable:Boolean})
const emit=defineEmits(['update:region','checked'])
const session=useSession(), report=ref(null), state=ref(''), retry=ref(0)
const wording={
  region:['지역 금제','Regional restrictions','地域別リミットレギュレーション'],
  basic:['기본 구성만 검사','Basic deck rules only','基本構成のみ確認'],
  OCG:['OCG (일본)','OCG (Japan)','OCG（日本）'],TCG:['TCG Advanced','TCG Advanced','TCG Advanced'],
  checking:['금지·제한 목록 확인 중…','Checking the restriction list…','禁止・制限リストを確認中…'],
  invalid:['수량을 입력하면 목록을 확인합니다.','Enter valid quantities to check the list.','正しい枚数を入力すると確認できます。'],
  error:['금지·제한 목록을 확인하지 못했습니다.','Could not check the restriction list.','禁止・制限リストを確認できませんでした。'],
  retry:['다시 확인','Retry check','再確認'],
  date:['시행일','Effective','適用日'],source:['공식 금지·제한 목록','Official restriction list','公式リミットレギュレーション'],
  checked:['목록에서 수량 초과가 발견되지 않았습니다.','No listed copy limit exceeded.','リスト上の枚数超過はありません。'],
  partial:['목록과 대조하지 못한 카드가 있습니다.','Some cards could not be checked.','リストと照合できないカードがあります。'],
  unavailable:['이 지역의 목록을 확인할 수 없습니다.','The list for this region is unavailable.','この地域のリストを確認できません。'],
  draft:['이 구성은 초안으로 저장할 수 있습니다.','You can save this deck as a draft.','この構成は下書きで保存できます。'],
  unknown:['미확인 카드','Unchecked cards','未確認のカード'],
  forbidden:['금지','Forbidden','禁止'],limited:['제한','Limited','制限'],semi:['준제한','Semi-limited','準制限'],
  included:['덱에 포함','In deck','デッキ内'],allowed:['허용','Allowed','上限'],
}
const text=key=>wording[key]?.[{ko:0,en:1,ja:2}[locale.value]??0]??key
const deckRows=computed(()=>props.entries.map(({cardId,section,quantity,variantId,neuronArtwork})=>({cardId,section,quantity,variantId,neuronArtwork})))
const signature=computed(()=>JSON.stringify(deckRows.value))
const names=computed(()=>new Map(props.entries.map(e=>[e.cardId,e.name])))
const current=computed(()=>props.editable?report.value:props.savedReport)
const accepted=computed(()=>current.value?.status==='CHECKED'&&!current.value.unknownCardIds?.length&&!current.value.violations?.length)
watch([()=>props.region,signature,retry],([region],_,cleanup)=>{
  report.value=null
  state.value=''
  if(!props.editable || !region)return
  emit('checked',false)
  if(deckRows.value.some(e=>!Number.isInteger(e.quantity)||e.quantity<1||e.quantity>999)){state.value='invalid';return}
  const controller=new AbortController()
  state.value='checking'
  const timer=setTimeout(async()=>{
    try{
      const result=await session.authenticatedRequest('/me/decks/yugioh-limits',{method:'POST',body:{region,entries:deckRows.value},signal:controller.signal})
      if(controller.signal.aborted)return
      if(result?.region!==region || !['CHECKED','PARTIAL','UNAVAILABLE'].includes(result.status))throw new Error()
      report.value=result;state.value='';emit('checked',accepted.value)
    }catch{if(!controller.signal.aborted)state.value='error'}
  },240)
  cleanup(()=>{clearTimeout(timer);controller.abort()})
},{immediate:true,flush:'sync'})
</script>
<template>
  <section class="regional-limits">
    <label v-if="editable">{{ text('region') }}
      <select :value="region" @change="$emit('update:region',$event.target.value)">
        <option value="">{{ text('basic') }}</option>
        <option v-for="code in regions" :key="code" :value="code">{{ text(code) }}</option>
      </select>
    </label>
    <h2 v-else>{{ text('region') }} · {{ text(region) }}</h2>
    <template v-if="region">
      <p v-if="state" role="status">{{ text(state) }} <button v-if="state==='error'" type="button" class="text-button" @click="retry++">{{ text('retry') }}</button></p>
      <div v-else-if="current" aria-live="polite">
        <p class="limits-source"><span v-if="current.effectiveOn">{{ text('date') }} <time :datetime="current.effectiveOn">{{ current.effectiveOn }}</time></span>
          <a v-if="sourceLink(current.sourceUrl)" :href="sourceLink(current.sourceUrl)" target="_blank" rel="noopener noreferrer">{{ text('source') }}</a></p>
        <p v-if="accepted">{{ text('checked') }}</p>
        <p v-if="current.status==='UNAVAILABLE'">{{ text('unavailable') }}</p>
        <p v-else-if="current.status==='PARTIAL'">{{ text('partial') }}</p>
        <ul v-if="current.violations?.length" class="limits-list"><li v-for="v in current.violations" :key="v.cardId">
          <strong>{{ text(['forbidden','limited','semi'][v.limit]||'allowed') }} · {{ names.get(v.cardId)||v.name }}</strong>
          <small>{{ text('included') }} {{ v.copies }} / {{ text('allowed') }} {{ v.limit }}</small>
        </li></ul>
        <details v-if="current.unknownCardIds?.length"><summary>{{ text('unknown') }} ({{ current.unknownCardIds.length }})</summary>
          <ul><li v-for="id in current.unknownCardIds" :key="id">{{ names.get(id)||('#'+id) }}</li></ul>
        </details>
      </div>
      <p v-else>{{ text('unavailable') }}</p>
      <small v-if="editable && !accepted && state!=='checking'">{{ text('draft') }}</small>
    </template>
  </section>
</template>
<style scoped>
.regional-limits{margin-block:1rem;min-width:0}.regional-limits label{display:grid;gap:.35rem}
.regional-limits p{margin:.45rem 0}.regional-limits small,.limits-source{color:var(--mu)}
.limits-source{display:flex;align-items:baseline;gap:.3rem .8rem;flex-wrap:wrap}.limits-source time{font-variant-numeric:tabular-nums}
.limits-list{list-style:none;padding:0;margin:.5rem 0}.limits-list li{border-inline-start:3px solid var(--bd);padding:.15rem .65rem;margin:.35rem 0}
.limits-list small{display:block}.regional-limits summary{cursor:pointer}
</style>
