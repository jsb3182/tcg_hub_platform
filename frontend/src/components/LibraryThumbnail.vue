<script setup>
import { computed, ref } from 'vue'
import ArtworkCredit from './ArtworkCredit.vue'
import { cardArtworks, preferredArtwork } from '../artwork'
import { locale } from '../i18n'
const props=defineProps({image:Object,src:String,language:String,showEdition:Boolean,printing:Object,disableLink:Boolean})
const failed=ref('')
const art=computed(()=>preferredArtwork(cardArtworks(props.src,props.language,[{image:props.image}],failed.value,props.printing?.imageBasis),locale.value))
</script>
<template>
  <img v-if="art?.src" :src="art.src" alt="" loading="lazy" class="lib-thumbnail inline-art" referrerpolicy="no-referrer" @error="failed=$event.target.getAttribute('src')">
  <span v-else-if="art?.style" class="lib-thumbnail" :style="art.style" aria-hidden="true"></span>
  <figcaption v-if="showEdition && art" class="art-language">
    <ArtworkCredit :language="art.language" automatic :printing="art.src ? printing : null" :disable-link="disableLink"/>
  </figcaption>
  <slot :art="art"/>
</template>

<style scoped>
.lib-thumbnail {display:block}
span.lib-thumbnail {background-size:400% 300%;background-repeat:no-repeat}
.art-language {color:var(--mu);font-size:.78rem}
.inline-art {object-fit:contain;aspect-ratio:300 / 438}
</style>
