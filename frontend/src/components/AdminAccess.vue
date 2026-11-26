<script setup>
import { t as uiText } from '../i18n'

import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useSession } from '../stores/session'

const props = defineProps({ entry: Boolean })
const session = useSession()
const phase = ref('checking')
const error = ref('')
const busy = ref(false)
const codeInput = ref(null)
const controller = new AbortController()

function openAdmin() {
  if (controller.signal.aborted) return
  session.adminAccessBlocked = false
  if (props.entry) window.location.replace('/admin')
}

async function check() {
  error.value = ''
  phase.value = 'checking'
  try {
    const mode = await session.loadAdminMode()
    if (controller.signal.aborted) return
    if (mode === 'DISABLED') { phase.value = 'disabled'; return }
    if (mode === 'CLOUDFLARE') {
      phase.value = 'cloudflare'
      if (props.entry) openAdmin()
      return
    }
    if (props.entry) {
      try {
        await session.adminRequest('/status', { signal: controller.signal })
        openAdmin()
        return
      } catch (cause) { if (cause.status !== 403) throw cause }
    }
    phase.value = 'code'
  } catch (cause) {
    if (controller.signal.aborted) return
    error.value = cause.message
    phase.value = 'error'
  }
}

async function verify() {
  if (busy.value || !codeInput.value?.validity.valid) return
  busy.value = true
  error.value = ''
  let accepted = false
  try {
    const verification = session.verifyLocalCode(codeInput.value.value, controller.signal)
    codeInput.value.value = ''
    await verification
    accepted = true
    // Confirm that the browser returned the HttpOnly cookie before protected navigation.
    await session.adminRequest('/status', { signal: controller.signal })
    openAdmin()
  } catch (cause) {
    if (controller.signal.aborted) return
    if (cause.status === 403) {
      error.value = accepted ? uiText("인증 쿠키를 확인할 수 없습니다. 이 사이트의 쿠키 설정을 확인해 주세요.")
        : uiText("인증에 실패했습니다. 등록한 인증 앱의 새 코드를 입력해 주세요.")
    } else error.value = cause.message
  } finally { busy.value = false }
}

onMounted(check)
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <form v-if="phase === 'code'" class="panel admin-verification" @submit.prevent="verify">
    <h2>{{ $t("인증 앱으로 본인 확인") }}</h2>
    <p>{{ $t("등록한 인증 앱에서 현재 6자리 코드를 확인해 주세요.") }}</p>
    <label>{{ $t("인증 코드") }}<input ref="codeInput" type="password" inputmode="numeric" autocomplete="one-time-code"
      pattern="[0-9]{6}" minlength="6" maxlength="6" required :disabled="busy" /></label>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <button class="primary wide" :disabled="busy" type="submit">{{ busy ? $t("확인 중…") : $t("인증하고 관리자 화면 열기") }}</button>
  </form>
  <p v-else-if="phase === 'checking'" class="state" role="status">{{ $t("관리자 인증 상태를 확인하는 중입니다.") }}</p>
  <p v-else-if="phase === 'disabled'" class="state" role="alert">{{ $t("이 주소에서는 관리자 화면을 사용할 수 없습니다.") }}</p>
  <section v-else-if="phase === 'cloudflare'" class="state">
    <p>{{ $t("관리자 접근 권한을 다시 확인해 주세요.") }}</p>
    <a href="/admin">{{ $t("Cloudflare Access 인증 다시 열기") }}</a>
  </section>
  <section v-else class="state"><p role="alert">{{ error }}</p><button class="secondary" @click="check">{{ $t("다시 확인") }}</button></section>
</template>
