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
    <p>{{ $route.name==='binder' ? '보유 카드와 수량을 저장하려면 로그인하세요.' : '덱을 만들고 저장하려면 로그인하세요.' }}</p>
    <RouterLink class="primary" :to="{name:'login',query:{next:route.fullPath}}">로그인</RouterLink>
    <RouterLink class="signup-link" :to="{name:'login',query:{mode:'register',next:route.fullPath}}">회원가입</RouterLink>
  </section>
  <slot v-else />
</template>

<style scoped>
.signup-link { display: inline-flex; align-items: center; min-height: 44px; margin-inline-start: 1rem; }
</style>
