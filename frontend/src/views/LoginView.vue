<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSession } from '../stores/session'
import AdminAccess from '../components/AdminAccess.vue'
const session = useSession()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const invalidField = ref('')
const busy = ref(false)
const heading = ref(null)
const emailInput = ref(null)
const passwordInput = ref(null)
const wantsAdmin = computed(() => route.query.to === 'admin' || ['/admin', '/admin/'].includes(route.query.next))
const registering = computed(() => !wantsAdmin.value && route.query.mode === 'register')
const title = computed(() => wantsAdmin.value ? '관리자 로그인' : registering.value ? '회원가입' : '로그인')
const destination = computed(() => {
  const next = route.query.next
  if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return '/'
  const target = router.resolve(next)
  return ['binder','decks','deck-edit','deck-new','play','stores'].includes(target.name) ? target.fullPath : '/'
})

const switchMode = computed(() => ({
  name: 'login',
  query: { next: route.query.next, mode: registering.value ? undefined : 'register' },
}))

watch(() => route.fullPath, () => {
  if (route.name === 'login') document.title = title.value + ' · TCG 허브'
}, { immediate: true, flush: 'post' })

watch(registering, async () => {
  password.value = ''
  error.value = invalidField.value = ''
  await nextTick()
  heading.value?.focus()
})

function fieldError(field, message) {
  invalidField.value = field
  error.value = message
  const input = field === 'email' ? emailInput : passwordInput
  input.value?.focus()
}

async function submit() {
  if (busy.value) return
  error.value = invalidField.value = ''
  const signup = registering.value
  if (signup) {
    if (!emailInput.value.validity.valid) return fieldError('email', '이메일 주소를 확인해 주세요.')
    if (!password.value.trim() || [...password.value].length < 12) {
      return fieldError('password', '비밀번호는 공백만으로 구성할 수 없으며 12자 이상이어야 합니다.')
    }
    if (new TextEncoder().encode(password.value).length > 72) {
      return fieldError('password', '비밀번호를 UTF-8 기준 72바이트 이내로 줄여 주세요.')
    }
  }
  const entry = route.fullPath
  const next = destination.value
  busy.value = true
  try {
    const attempt = signup ? session.register(email.value.trim(), password.value) : session.login(email.value.trim(), password.value)
    if (!signup) password.value = ''
    await attempt
    password.value = ''
    if (entry === route.fullPath && !wantsAdmin.value) await router.replace(next)
  } catch (cause) {
    if (entry !== route.fullPath) return
    if (signup && cause.status === 409) fieldError('email', '이미 가입된 이메일입니다. 로그인하거나 다른 이메일을 입력해 주세요.')
    else if (signup && cause.status === 400) error.value = '이메일 주소와 비밀번호 조건을 확인해 주세요.'
    else error.value = cause.status === 401 ? '이메일 또는 비밀번호를 확인해 주세요.' : cause.message
  }
  finally { busy.value = false }
}
</script>

<template>
  <div class="compact-page">
    <h1 ref="heading" tabindex="-1">{{ title }}</h1>
    <AdminAccess v-if="wantsAdmin && session.isAdmin" entry />
    <section v-else-if="session.account" class="panel">
      <p>{{ session.account.email }} 계정으로 로그인했습니다.</p>
      <p v-if="wantsAdmin">이 계정에는 관리자 권한이 없습니다.</p><RouterLink to="/">도감 열기</RouterLink>
    </section>
    <form v-else class="panel" :novalidate="registering" :aria-busy="busy" @submit.prevent="submit">
      <label>이메일<input ref="emailInput" v-model="email" type="email" required maxlength="254" autocomplete="username"
        autocapitalize="none" spellcheck="false" :readonly="busy" :aria-invalid="invalidField==='email' || undefined"
        :aria-describedby="invalidField==='email' ? 'auth-error' : undefined" /></label>
      <label>비밀번호<input ref="passwordInput" v-model="password" type="password" required :readonly="busy"
        :autocomplete="registering ? 'new-password' : 'current-password'" :aria-invalid="invalidField==='password' || undefined"
        :aria-describedby="invalidField==='password' ? 'password-rule auth-error' : registering ? 'password-rule' : undefined" /></label>
      <p v-if="registering" id="password-rule" class="password-rule">12자 이상, UTF-8 기준 72바이트 이내</p>
      <p v-if="error" id="auth-error" role="alert" class="inline-error">{{ error }}</p>
      <button type="submit" class="primary wide" :disabled="busy || !session.ready">{{ registering ? (busy ? '가입 중…' : '회원가입') : (busy ? '로그인 중…' : '로그인') }}</button>
    </form>
    <p v-if="!wantsAdmin && !session.account" class="switch-auth">
      {{ registering ? '이미 계정이 있으신가요?' : '처음 방문하셨나요?' }}
      <RouterLink :to="switchMode">{{ registering ? '로그인' : '회원가입' }}</RouterLink>
    </p>
  </div>
</template>

<style scoped>
.password-rule, .switch-auth { color: var(--mu); font-size: .9rem; }
.password-rule { margin: -.3rem 0 1rem; }
.switch-auth a { display: inline-flex; align-items: center; min-height: 44px; margin-inline-start: .35rem; }
</style>
