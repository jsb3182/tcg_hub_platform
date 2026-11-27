<script setup>
import {computed} from 'vue'
import {locale} from '../i18n'
import {pt} from '../pack'
const props=defineProps({month:String,items:Array,asOf:String,day:String})
const emit=defineEmits(['select','month'])
const weekdays=computed(()=>Array.from({length:7},(_,i)=>new Intl.DateTimeFormat(locale.value,{weekday:'short',timeZone:'UTC'}).format(Date.UTC(2023,0,i+1))))
const start=computed(()=>new Date(props.month+'-01T00:00:00Z'))
const title=computed(()=>new Intl.DateTimeFormat(locale.value,{year:'numeric',month:'long',timeZone:'UTC'}).format(start.value))
const dates=computed(()=>{
  const dayCount=new Date(Date.UTC(start.value.getUTCFullYear(),start.value.getUTCMonth()+1,0)).getUTCDate()
  const counts=new Map()
  for(const row of props.items||[])counts.set(row.releaseDate,(counts.get(row.releaseDate)||0)+1)
  return Array.from({length:dayCount},(_,i)=>{
    const iso=props.month+'-'+String(i+1).padStart(2,'0')
    return {iso,number:i+1,count:counts.get(iso)||0}
  })
})
</script>
<template>
  <section class="month-picker" :aria-label="pt('월간 달력')">
    <div class="month-toolbar">
      <button type="button" class="text-button" :aria-label="pt('이전 달')" @click="emit('month',-1)">‹</button>
      <h3>{{ title }}</h3>
      <button type="button" class="text-button" :aria-label="pt('다음 달')" @click="emit('month',1)">›</button>
    </div>
    <div class="date-grid">
      <small v-for="name in weekdays" :key="name" aria-hidden="true">{{ name }}</small>
      <span v-for="i in start.getUTCDay()" :key="'blank'+i" aria-hidden="true"></span>
      <template v-for="d in dates" :key="d.iso">
        <button v-if="d.count" type="button" :aria-pressed="day===d.iso" :aria-label="d.iso+' · '+pt('일정')+' '+d.count"
          :aria-current="d.iso===asOf?'date':null" @click="emit('select',day===d.iso?'':d.iso)">{{ d.number }}<small>{{ d.count }}</small></button>
        <span v-else :aria-current="d.iso===asOf?'date':null">{{ d.number }}</span>
      </template>
    </div>
    <button v-if="day" type="button" class="text-button" @click="emit('select','')">{{ pt('이 달의 전체 일정') }}</button>
  </section>
</template>
<style scoped>
.month-picker{margin-top:1rem}.month-toolbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--bd)}
.month-toolbar h3{font-size:1.02rem;margin:0}.month-toolbar button{font-size:1.35rem;min-width:44px;min-height:44px}
.date-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:1px}.date-grid>small,.date-grid>span,.date-grid>button{text-align:center;min-width:0;font-variant-numeric:tabular-nums}
.date-grid>small{padding:.45rem 0}.date-grid>span,.date-grid>button{display:flex;align-items:center;justify-content:center;gap:2px;min-height:44px;border-radius:4px}
.date-grid>span{color:var(--mu);font-size:.84rem}.date-grid>button{border:1px solid var(--bd);color:var(--tx);background:var(--sf);font-size:.88rem;padding:1px}
.date-grid button small{color:var(--ac);font-size:.65rem;align-self:end}.date-grid>[aria-current=date]{text-decoration:underline}
.date-grid button[aria-pressed=true]{border:2px solid var(--ac);font-weight:700}
</style>
