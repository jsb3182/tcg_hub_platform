<script setup>
import { ref, watch } from 'vue'
import { useSession } from '../stores/session'
const session = useSession()
const status = ref(null)
const error = ref('')
const busy = ref(false)
async function load() {
  error.value = ''
  status.value = null
  if (!session.isAdmin) return
  busy.value = true
  try { status.value = await session.adminStatus() }
  catch (cause) { error.value = cause.message }
  finally { busy.value = false }
}
watch(() => session.isAdmin, load, { immediate: true })
</script>

<template>
  <div class="compact-page"><h1>관리자</h1>
    <section class="panel">
      <p v-if="!session.ready" role="status">로그인 상태를 확인하는 중입니다.</p>
      <template v-else-if="!session.account"><p>관리자 계정으로 로그인해 주세요.</p><RouterLink :to="{name: 'login', query: {to: 'admin'}}">로그인</RouterLink></template>
      <p v-else-if="!session.isAdmin" role="alert">관리자 권한이 필요합니다.</p>
      <template v-else>
        <h2>서버 상태</h2>
        <p v-if="busy" role="status">상태를 확인하는 중입니다.</p>
        <p v-else-if="error" role="alert">{{ error }}</p>
        <dl v-else-if="status" class="specs"><div><dt>API 상태</dt><dd>{{ status.status === 'UP' ? '정상' : status.status }}</dd></div><div><dt>접속 계정</dt><dd>{{ status.user }}</dd></div></dl>
        <button class="secondary" type="button" :disabled="busy" @click="load">상태 새로고침</button>
      </template>
    </section>
  </div>
</template>
