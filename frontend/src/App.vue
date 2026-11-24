<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSession } from './stores/session'

const session = useSession()
const router = useRouter()
const online = ref(navigator.onLine)
const logoutError = ref('')
const busy = ref(false)
const updateOnline = () => { online.value = navigator.onLine }
onMounted(() => {
  session.initialize()
  window.addEventListener('online', updateOnline)
  window.addEventListener('offline', updateOnline)
})
onUnmounted(() => {
  window.removeEventListener('online', updateOnline)
  window.removeEventListener('offline', updateOnline)
})
async function logout() {
  busy.value = true
  logoutError.value = ''
  try {
    await session.logout()
    if (router.currentRoute.value.name === 'admin') await router.replace('/')
  } catch (cause) { logoutError.value = cause.message }
  finally { busy.value = false }
}
</script>

<template>
  <a class="skip" href="#content">본문 바로가기</a>
  <header class="masthead">
    <div class="shell masthead-inner">
      <RouterLink to="/" class="brand" aria-label="TCG 허브 홈">
        <img src="/icon-192.png" width="32" height="32" alt="" /> TCG <b>허브</b>
      </RouterLink>
      <nav aria-label="주 메뉴">
        <RouterLink to="/">카드 도감</RouterLink>
        <RouterLink to="/news">새 소식</RouterLink>
        <a v-if="session.isAdmin" href="/admin">관리자</a>
        <span class="divider" aria-hidden="true"></span>
        <button v-if="session.account" type="button" class="text-button" :disabled="busy" @click="logout">로그아웃</button>
        <RouterLink v-else to="/login">로그인</RouterLink>
      </nav>
    </div>
  </header>
  <div v-if="!online" class="notice shell" role="status">오프라인입니다. 최근 열어 본 도감 페이지와 이미지를 조회할 수 있습니다.</div>
  <div v-if="logoutError" class="notice shell" role="alert">{{ logoutError }}</div>
  <main id="content" class="shell" tabindex="-1"><RouterView /></main>
  <footer class="shell footer">카드 이름과 이미지의 권리는 각 권리자에게 있습니다.</footer>
</template>
