<script setup>
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {publicPacks} from '../legacyPacks'
import {locale} from '../i18n'
import {packTitle} from '../pack'

const props=defineProps({pack:{type:Object,required:true}})
const root=ref(),packs=ref([]),route=useRoute(),router=useRouter()
const words={ko:['팩 이동','이전 팩','다음 팩'],en:['Set navigation','Previous set','Next set'],ja:['商品間の移動','前の商品','次の商品']}
const labels=computed(()=>words[locale.value]||words.ko)
const neighbors=computed(()=>{
  const group=packs.value.filter(p=>p.group===props.pack.group && p.gameCode===props.pack.gameCode && (p.metadata?.id || p.officialProduct))
  const i=group.findIndex(p=>p.id===props.pack.id)
  return i===-1?[]:[group[i-1],group[i+1]]
})
function target(pack){return {name:'pack',params:{id:pack.id},query:route.query}}
let start,area
function touchStart(event){
  start=null
  if(event.touches.length!==1 || document.querySelector('dialog[open]') ||
     event.target.closest('a,button,summary,input,select,textarea,[role="slider"]'))return
  const finger=event.touches[0]
  if(finger.clientX>24 && finger.clientX<window.innerWidth-24)start=[finger.clientX,finger.clientY]
}
function touchEnd(event){
  const point=start
  start=null
  if(!point || event.touches.length || !event.changedTouches.length || window.getSelection()?.toString())return
  const dx=event.changedTouches[0].clientX-point[0],dy=event.changedTouches[0].clientY-point[1]
  const next=neighbors.value[dx<0?1:0]
  if(next && Math.abs(dx)>=90 && Math.abs(dx)>Math.abs(dy)*2.5)router.replace(target(next))
}
function cancel(){start=null}
onMounted(async()=>{
  area=root.value.closest('.pack-page')
  area?.addEventListener('touchstart',touchStart,{passive:true})
  area?.addEventListener('touchend',touchEnd,{passive:true})
  area?.addEventListener('touchcancel',cancel,{passive:true})
  try {packs.value=await publicPacks()} catch { /* A loaded pack remains readable offline. */ }
})
onBeforeUnmount(()=>{
  area?.removeEventListener('touchstart',touchStart)
  area?.removeEventListener('touchend',touchEnd)
  area?.removeEventListener('touchcancel',cancel)
})
</script>
<template>
  <div ref="root">
    <nav v-if="neighbors.some(Boolean)" class="neighbors" :aria-label="labels[0]">
      <template v-for="(pack,index) in neighbors" :key="index">
        <RouterLink v-if="pack" :class="{next:index===1}" :to="target(pack)">
          <small>{{ labels[index+1] }}</small><span>{{ packTitle(pack) }}</span>
        </RouterLink>
      </template>
    </nav>
  </div>
</template>
<style scoped>
.neighbors{display:grid;grid-template-columns:1fr 1fr;gap:1rem;border-top:1px solid var(--bd);margin-top:1.5rem}
.neighbors a{display:grid;align-content:center;min-height:48px;padding:.55rem 0;text-decoration:none;color:var(--tx);overflow-wrap:anywhere}
.neighbors a:hover span,.neighbors a:focus-visible span{text-decoration:underline}.neighbors small{color:var(--mu)}
.neighbors .next{grid-column:2;text-align:end}
</style>
