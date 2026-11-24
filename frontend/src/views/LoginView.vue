<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSession } from '../stores/session'
import AdminAccess from '../components/AdminAccess.vue'
const session = useSession()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const wantsAdmin = computed(() => route.query.to === 'admin' || ['/admin', '/admin/'].includes(route.query.next))

async function login() {
  busy.value = true
  error.value = ''
  try {
    const attempt = session.login(email.value.trim(), password.value)
    password.value = ''
    await attempt
    if (!wantsAdmin.value) await router.replace('/')
  } catch (cause) { error.value = cause.status === 401 ? '이메일 또는 비밀번호를 확인해 주세요.' : cause.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="compact-page">
    <h1>{{ wantsAdmin ? '관리자 로그인' : '로그인' }}</h1>
    <AdminAccess v-if="wantsAdmin && session.isAdmin" entry />
    <section v-else-if="session.account" class="panel">
      <p>{{ session.account.email }} 계정으로 로그인했습니다.</p>
      <p v-if="wantsAdmin">이 계정에는 관리자 권한이 없습니다.</p><RouterLink to="/">도감 열기</RouterLink>
    </section>
    <form v-else class="panel" @submit.prevent="login">
      <label>이메일<input v-model="email" type="email" required maxlength="254" autocomplete="username" /></label>
      <label>비밀번호<input v-model="password" type="password" required autocomplete="current-password" /></label>
      <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
      <button type="submit" class="primary wide" :disabled="busy || !session.ready">{{ busy ? '로그인 중…' : '로그인' }}</button>
    </form>
  </div>
</template>
