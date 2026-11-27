<script setup>
import { computed, ref } from 'vue'
import ArtworkCredit from './ArtworkCredit.vue'
import { cardArtworks, preferredArtwork } from '../artwork'
import { locale } from '../i18n'
import {pt} from '../pack'
const props=defineProps({image:Object,src:String,language:String,showEdition:Boolean,placeholder:Boolean,printing:Object,disableLink:Boolean})
const failed=ref('')
const art=computed(()=>preferredArtwork(cardArtworks(props.src,props.language,[{image:props.image}],failed.value,props.printing?.imageBasis),locale.value))
</script>
<template>
  <img v-if="art?.src" :src="art.src" alt="" loading="lazy" class="lib-thumbnail inline-art" referrerpolicy="no-referrer" @error="failed=$event.target.getAttribute('src')">
  <span v-else-if="art?.style" class="lib-thumbnail" :style="art.style" aria-hidden="true"></span>
  <span v-else-if="placeholder" class="lib-thumbnail empty-art" role="img" :aria-label="pt('로컬 이미지 없음')" :title="pt('로컬 이미지 없음')"><span aria-hidden="true">—</span></span>
  <figcaption v-if="showEdition && art" class="art-language">
    <ArtworkCredit :language="art.language" automatic :printing="art.src ? printing : null" :disable-link="disableLink"/>
  </figcaption>
  <slot :art="art"/>
</template>

<style scoped>
.lib-thumbnail {display:block;width:var(--thumbnail-width,36px);min-width:0;max-width:100%;height:auto}
span.lib-thumbnail {background-size:400% 300%;background-repeat:no-repeat}
.art-language {color:var(--mu);font-size:.78rem}
.inline-art {object-fit:contain;aspect-ratio:300 / 438}
.empty-art{display:grid;place-content:center;aspect-ratio:300/438;border:1px dashed var(--bd);color:var(--mu);background:var(--bg);font-size:.7rem}
</style>
