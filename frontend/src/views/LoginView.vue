<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSession } from '../stores/session'
const session = useSession()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function login() {
  busy.value = true
  error.value = ''
  try {
    await session.login(email.value.trim(), password.value)
    password.value = ''
    if (route.query.to === 'admin' && session.isAdmin) window.location.assign('/admin')
    else await router.replace('/')
  } catch (cause) { error.value = cause.status === 401 ? '이메일 또는 비밀번호를 확인해 주세요.' : cause.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="compact-page">
    <h1>로그인</h1>
    <section v-if="session.account" class="panel"><p>{{ session.account.email }} 계정으로 로그인했습니다.</p><RouterLink to="/">도감 열기</RouterLink></section>
    <form v-else class="panel" @submit.prevent="login">
      <label>이메일<input v-model="email" type="email" required maxlength="254" autocomplete="username" /></label>
      <label>비밀번호<input v-model="password" type="password" required autocomplete="current-password" /></label>
      <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
      <button type="submit" class="primary wide" :disabled="busy || !session.ready">{{ busy ? '로그인 중…' : '로그인' }}</button>
    </form>
  </div>
</template>
