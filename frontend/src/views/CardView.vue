<script setup>
import { useRoute } from 'vue-router'
import CardDetails from '../components/CardDetails.vue'
const route = useRoute()
</script>
<template><div class="standalone"><RouterLink :to="{name:'catalog',query:route.query}" class="back-link">{{ $t("도감 목록") }}</RouterLink><CardDetails :card-id="route.params.id" /></div></template>
