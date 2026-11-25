<script setup>
import { useSession } from '../stores/session'
import { useRoute } from 'vue-router'
import '../styles/library.css'
const session = useSession()
const route = useRoute()
defineProps({ title: { type: String, required: true } })
</script>
<template>
  <div v-if="!session.ready" role="status" class="state">로그인 상태를 확인하고 있습니다.</div>
  <section v-else-if="!session.account" class="compact-page">
    <h1>{{ title }}</h1>
    <p>로그인하면 내 카드와 덱을 계정에 저장할 수 있습니다.</p>
    <RouterLink class="primary" :to="{name:'login',query:{next:route.fullPath}}">로그인</RouterLink>
  </section>
  <slot v-else />
</template>
