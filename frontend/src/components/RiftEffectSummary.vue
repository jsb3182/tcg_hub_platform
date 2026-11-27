<script setup>
import {computed} from 'vue'
import {locale} from '../i18n'
import {riftEffectText} from '../riftSymbols'
const props=defineProps({card:{type:Object,required:true}})
const text=computed(()=>props.card.effectLanguage===locale.value?riftEffectText(props.card.effect,locale.value):'')
</script>
<template><small v-if="text" class="rift-excerpt" :lang="locale">{{ text }}</small></template>
<style scoped>
.rift-excerpt{display:-webkit-box!important;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:.78rem;font-weight:400;line-height:1.35;color:var(--mu);overflow-wrap:anywhere}
details[open]>summary .rift-excerpt{display:none!important}
</style>
