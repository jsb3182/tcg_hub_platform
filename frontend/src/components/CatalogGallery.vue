<script setup>
import { locale, supportedLanguage } from '../i18n'
import { pt, shortRarity } from '../pack'
import LibraryThumbnail from './LibraryThumbnail.vue'
import ArtworkCredit from './ArtworkCredit.vue'

defineProps({ cards:{type:Array,required:true}, query:{type:Object,required:true} })
</script>

<template>
  <ul class="catalog-gallery" :aria-label="pt('카드 배열')">
    <li v-for="card in cards" :key="card.id">
      <RouterLink :to="{name:'card',params:{id:card.id},query:{...query,lang:locale}}">
        <LibraryThumbnail v-slot="{ art }" :image="card.image" :src="card.imageUrl"
          :language="card.imageLanguage" :printing="card">
          <span v-if="!art?.src && !art?.style" class="no-picture">{{ pt('로컬 이미지 없음') }}</span>
          <span class="tile-title" :lang="locale">{{ card.language===locale && card.name ? card.name : card.number }}</span>
          <span class="tile-meta">{{ [card.language===locale && card.name ? card.number : '', shortRarity(card)].filter(Boolean).join(' · ') }}</span>
          <small v-if="art && (art.reference || art.language!==locale)" class="tile-credit">
            <ArtworkCredit :language="art.language" :label-image="!supportedLanguage(art.language)"
              :printing="art.src ? card : null" automatic disable-link />
          </small>
        </LibraryThumbnail>
      </RouterLink>
    </li>
  </ul>
</template>

<style scoped>
.catalog-gallery {
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(108px,1fr));
  gap:18px 12px;
  margin:0;
  padding:0;
  list-style:none;
}
.catalog-gallery li{min-width:0}
.catalog-gallery a{display:block;color:var(--tx);text-decoration:none;overflow-wrap:anywhere;border-radius:4px}
.catalog-gallery a:hover .tile-title{text-decoration:underline;text-underline-offset:.18em}
.catalog-gallery :deep(.lib-thumbnail),.no-picture {
  width:100%;aspect-ratio:300/438;border-radius:4px;
}
.catalog-gallery :deep(img.lib-thumbnail){object-fit:contain;background:var(--bg)}
.no-picture{display:grid;place-items:center;text-align:center;padding:8px;border:1px dashed var(--bd);color:var(--mu);font-size:.76rem}
.tile-title,.tile-meta,.tile-credit{display:block}
.tile-title{margin-block-start:5px;font-size:.9rem;font-weight:650;line-height:1.35}
.tile-meta,.tile-credit{font-size:.75rem;color:var(--mu);line-height:1.4}
.tile-meta{font-variant-numeric:tabular-nums}
@media(max-width:600px){
  .catalog-gallery{grid-template-columns:repeat(auto-fill,minmax(78px,1fr));gap:14px 8px}
  .tile-title{font-size:.81rem}
}
</style>
