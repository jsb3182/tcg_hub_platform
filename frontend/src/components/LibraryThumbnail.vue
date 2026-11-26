<script setup>
import { computed, ref } from 'vue'
import { mediaPath, artworkUrl } from '../api'
const props=defineProps({image:Object,src:String})
const failed=ref('')
const art=computed(()=>artworkUrl(props.src))
const style=computed(()=>{
  const tile=props.image, url=mediaPath(tile?.url)
  if(!url || !Number.isInteger(tile.col) || !Number.isInteger(tile.row))return null
  return {backgroundImage:'url("'+url.replace(/"/g,'%22')+'")',backgroundPosition:(tile.col*100/3)+'% '+(tile.row*50)+'%',
    aspectRatio:tile.cellWidth+' / '+tile.cellHeight}
})
</script>
<template><img v-if="art && failed!==art" :src="art" alt="" loading="lazy" class="lib-thumbnail inline-art" referrerpolicy="no-referrer" @error="failed=art"><span v-else-if="style" class="lib-thumbnail" :style="style" aria-hidden="true"></span></template>

<style scoped>.inline-art{object-fit:contain;aspect-ratio:300 / 438}</style>
