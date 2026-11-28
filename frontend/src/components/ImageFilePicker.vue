<script setup>
defineProps({ label:{type:String,required:true}, action:{type:String,required:true}, name:String, disabled:Boolean })
const emit=defineEmits(['select'])
function choose(event) {
  const file=event.target.files[0]
  event.target.value=''
  if(file) emit('select',file)
}
</script>

<template>
  <label class="image-file-picker" :class="{disabled}">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m4 17 5-5 3 3 3-4 5 6"/>
    </svg>
    <span>{{ action }}<small v-if="name">{{ name }}</small></span>
    <input type="file" :aria-label="label" :disabled="disabled" accept="image/png,image/jpeg,image/webp" @change="choose">
  </label>
</template>

<style scoped>
.image-file-picker{display:flex;position:relative;align-items:center;gap:12px;min-height:54px;padding:9px 12px;border:1px dashed var(--bd);border-radius:8px;color:var(--ac);cursor:pointer}
.image-file-picker svg{flex:none}
.image-file-picker span{font-weight:650;min-width:0}
.image-file-picker small{display:block;color:var(--mu);font-weight:400;overflow-wrap:anywhere}
.image-file-picker input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer}
.image-file-picker:focus-within{outline:2px solid var(--ac);outline-offset:2px}
.image-file-picker.disabled{opacity:.65}
</style>
