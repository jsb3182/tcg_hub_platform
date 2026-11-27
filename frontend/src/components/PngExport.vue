<script setup>
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { pt } from '../pack'
import { savePng } from '../savePng'

const props=defineProps({render:{type:Function,required:true},name:String,label:String,chooseWidth:Boolean,quickSave:Boolean,summary:String,renderKey:String})
const preview=ref(null), trigger=ref(null), url=ref(''), blob=shallowRef(null), width=ref(580), busy=ref(false), error=ref('')
let active=true,timeout
const saved=ref(false)
function clean(){
  if(url.value) URL.revokeObjectURL(url.value)
  url.value='';blob.value=null
}
function open(){
  clean(); error.value='';saved.value=false
  preview.value.showModal()
  if(!props.chooseWidth) generate()
}
async function generate(){
  if(busy.value) return
  busy.value=true; error.value=''
  try {
    const image=await props.render(width.value)
    if(!image) throw new Error()
    if(active && preview.value?.open){ clean(); blob.value=image;url.value=URL.createObjectURL(image) }
  }catch{ if(active) error.value=pt('이미지를 저장하지 못했습니다. 다시 시도해 주세요.') }
  finally{if(active) busy.value=false}
}
async function save(makeNew=false) {
  if(busy.value)return
  busy.value=true;error.value=''
  try{
    const image=makeNew ? await props.render(width.value) : blob.value
    if(!image)throw new Error()
    await savePng(image,(props.name || 'cards').replace(/[<>:"/\\|?*]/g,'_').slice(0,120)+'.png')
    if(active){saved.value=true;clearTimeout(timeout);timeout=setTimeout(()=>saved.value=false,2700)}
  }catch{if(active)error.value=pt('이미지를 저장하지 못했습니다. 다시 시도해 주세요.')}
  finally{if(active)busy.value=false}
}
function close(){ preview.value.close() }
function closed(){ clean(); trigger.value?.focus({preventScroll:true}) }
watch(()=>props.renderKey,()=>{if(preview.value?.open)clean()})
onBeforeUnmount(()=>{active=false;clean();clearTimeout(timeout)})
</script>
<template>
  <button v-if="quickSave" class="secondary pack-export" type="button" :disabled="busy" @click="save(true)">{{ label }}</button>
  <button ref="trigger" class="secondary pack-export" type="button" :disabled="busy" @click="open">{{ quickSave?pt('이미지 미리보기'):label }}</button>
  <p v-if="error && quickSave && !preview?.open" class="inline-error" role="alert">{{ error }}</p>
  <p v-if="saved && !preview?.open" role="status" class="save-notice">{{ pt('PNG 저장을 요청했습니다.') }}</p>
  <dialog ref="preview" class="pack-save" :aria-label="label" @close="closed" @click="e=>{if(e.target===preview)close()}">
    <section>
      <header><h2>{{ label }}</h2><button class="text-button" type="button" @click="close">{{ pt('닫기') }}</button></header>
      <p v-if="summary">{{ summary }}</p>
      <fieldset v-if="$slots.default" :disabled="busy" class="save-options"><slot/></fieldset>
      <template v-if="!url">
        <label v-if="chooseWidth">{{ pt('이미지 가로 폭') }}
          <select v-model.number="width" :disabled="busy"><option v-for="size in [360,580,720]" :key="size" :value="size">{{ size }} px</option></select>
        </label>
        <p v-if="busy" role="status">{{ pt('이미지 만드는 중…') }}</p>
        <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
        <button v-if="chooseWidth || error || summary" type="button" class="primary" :disabled="busy" @click="generate">{{ pt(error?'다시 시도':'이미지 만들기') }}</button>
      </template>
      <template v-else>
        <img :src="url" :alt="name"><p>{{ pt('길게 누르거나 다운로드하세요.') }}</p>
        <p v-if="error" role="alert" class="inline-error">{{ error }}</p><button class="pack-download" type="button" :disabled="busy" @click="save()">{{ pt('PNG 파일 다운로드') }}</button>
        <p v-if="saved" role="status" class="save-notice">{{ pt('PNG 저장을 요청했습니다.') }}</p>
      </template>
    </section>
  </dialog>
</template>
<style scoped>
.save-options{border:0;margin:.6rem 0;padding:0}.save-notice{position:fixed;inset:auto auto calc(66px + env(safe-area-inset-bottom)) 50%;transform:translateX(-50%);z-index:5;pointer-events:none;width:max-content;max-width:90%;margin:0;padding:.45rem .9rem;background:var(--tx);color:var(--sf);border-radius:999px;font-size:.85rem;text-align:center}
@media(max-width:600px){dialog.pack-save{margin:auto 0 0;width:100%;max-width:100%;border-radius:16px 16px 0 0;padding-bottom:env(safe-area-inset-bottom)}}
.pack-export{min-height:44px}.pack-save{width:min(480px,calc(100% - 30px));max-height:85vh;border:1px solid var(--bd);border-radius:14px;background:var(--sf);color:var(--tx);padding:0}.pack-save::backdrop{background:rgb(0 0 0 / .55)}
.pack-save section{padding:18px}.pack-save header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.pack-save h2{font-size:1.1rem;margin:0}.pack-save header button{min-width:44px;min-height:44px}.pack-save img{display:block;max-width:100%;max-height:46vh;object-fit:contain;margin:auto}.pack-download{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:5px 14px;border-radius:8px;background:var(--ac);color:var(--sf);font-weight:650;text-decoration:none}
</style>
