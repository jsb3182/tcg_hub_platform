<script setup>
import {ref,watch,onBeforeUnmount} from 'vue'
import {t} from '../i18n'
import {useSession} from '../stores/session'
import {prepareDeckPicture,savedDeckPicture} from '../deckPictures'
const props=defineProps({id:[Number,String],pictures:Object,disabled:Boolean})
const emit=defineEmits(['pick'])
const session=useSession(), saved=ref({}), previews=ref({}),message=ref(''),working=ref(false)
const fields=[['cover','대표 이미지'],['main','메인 슬리브'],['extra','엑스트라 슬리브']]
watch(()=>props.pictures,(_,__,cleanup)=>{
  const urls=Object.fromEntries(Object.entries(props.pictures||{}).map(([slot,f])=>[slot,URL.createObjectURL(f)]))
  previews.value=urls;cleanup(()=>Object.values(urls).forEach(url=>URL.revokeObjectURL(url)))
},{immediate:true,deep:true})
let active=true;onBeforeUnmount(()=>{active=false})
async function load(e){
  if(!e.target.open || !props.id)return
  const id=props.id
  try{
    const images=await Promise.all(fields.map(async ([slot])=>[slot,(await session.authenticatedRequest('/me/decks/'+id+'/decoration/'+slot)).image]))
    if(active&&props.id===id)saved.value=Object.fromEntries(images.map(([key,value])=>[key,savedDeckPicture(value)]))
  }catch(cause){if(active)message.value=cause.message}
}
async function choose(slot,e){
  const file=e.target.files[0];if(!file)return
  const id=props.id;working.value=true;message.value=''
  try{const image=await prepareDeckPicture(file,slot);if(active&&id===props.id)emit('pick',slot,image)}
  catch{message.value=t('이미지를 읽지 못했습니다. 10MB 이하의 PNG, JPEG 또는 WebP를 선택하세요.')}
  finally{working.value=false;e.target.value=''}
}
</script>
<template><details class="deck-pictures" @toggle="load"><summary>{{ t('대표 이미지와 슬리브') }}</summary>
  <div class="picture-fields"><label v-for="[slot,title] in fields" :key="slot">{{ t(title) }}
    <img v-if="previews[slot]||saved[slot]" :src="previews[slot]||saved[slot]" alt="" :class="slot">
    <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="disabled||working" @change="choose(slot,$event)"></label></div>
  <p v-if="message" role="alert">{{ message }}</p></details></template>
<style scoped>.deck-pictures{padding-block:.8rem;border-block:1px solid var(--bd);margin-block:.75rem}.deck-pictures summary{font-weight:650}.picture-fields{display:grid;gap:.5rem}.picture-fields label{display:grid;gap:.4rem}.picture-fields input{width:100%;font-size:.85rem}.picture-fields img{width:3.2rem;height:auto}.picture-fields img.cover{width:9rem}</style>
