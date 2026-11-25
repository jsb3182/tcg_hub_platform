<script setup>
import { computed } from 'vue'
import { mediaPath } from '../api'
const props=defineProps({image:Object})
const style=computed(()=>{
  const tile=props.image, url=mediaPath(tile?.url)
  if(!url || !Number.isInteger(tile.col) || !Number.isInteger(tile.row))return null
  return {backgroundImage:'url("'+url.replace(/"/g,'%22')+'")',backgroundPosition:(tile.col*100/3)+'% '+(tile.row*50)+'%',
    aspectRatio:tile.cellWidth+' / '+tile.cellHeight}
})
</script>
<template><span v-if="style" class="lib-thumbnail" :style="style" aria-hidden="true"></span></template>
