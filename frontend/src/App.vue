<script setup>

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { languages, locale, selectLocale, supportedLanguage, t } from './i18n'
import { useSession } from './stores/session'
import DeckPageJump from './components/DeckPageJump.vue'

const session = useSession()
const router = useRouter()
watch(() => router.currentRoute.value.query.lang, code => {
  if (supportedLanguage(code)) selectLocale(code)
}, {immediate:true})
function changeLanguage(code) {
  if (!supportedLanguage(code)) return
  selectLocale(code)
  const route = router.currentRoute.value
  if (route.name==='login' && typeof route.query.next==='string' && route.query.next.startsWith('/') && !route.query.next.startsWith('//') && !route.query.next.includes('\\')) {
    const next = router.resolve(route.query.next)
    if (['play','decks','deck-edit','deck-new'].includes(next.name)) {
      const destination=router.resolve({path:next.path,query:{...next.query,lang:code},hash:next.hash})
      router.replace({path:route.path,query:{...route.query,next:destination.fullPath}})
      return
    }
  }
  if (route.query.lang || ['news','play','deck-edit','deck-new','decks'].includes(route.name)) {
    router.replace({path:route.path,query:{...route.query,lang:code},hash:route.hash})
  }
}
const online = ref(navigator.onLine)
const logoutError = ref('')
const busy = ref(false)
const menuOpen = ref(false)
const menuButton = ref(null)
const loginTarget = computed(() => {
  const route = router.currentRoute.value
  if (route.name === 'admin') return {name:'login',query:{to:'admin'}}
  if (route.name === 'login') return {name:'login',query:{next:route.query.next,to:route.query.to}}
  if (['binder','decks','deck-new','deck-edit','play','stores'].includes(route.name)) return {name:'login',query:{next:route.fullPath}}
  return {name:'login'}
})
const navigation = [
  {to:'/', label:'카드 도감', pages:['catalog','card']}, {to:'/releases',label:'발매 일정',pages:['releases','pack']},
  {to:'/news', label:'새 소식', pages:['news']},
  {to:'/stores', label:'매장 지도', pages:['stores']}, {to:'/binder', label:'바인더', pages:['binder']},
  {to:'/decks', label:'내 덱', pages:['decks','deck-new','deck-edit','shared-deck']}, {to:'/play', label:'플레이', pages:['play']},
]
watch(() => router.currentRoute.value.fullPath, () => { menuOpen.value = false })
function escapeMenu() {
  if (menuOpen.value) { menuOpen.value = false; menuButton.value?.focus() }
}
const updateOnline = () => { online.value = navigator.onLine }
onMounted(() => {
  session.initialize()
  session.loadAdminMode().catch(() => {})
  window.addEventListener('online', updateOnline)
  window.addEventListener('offline', updateOnline)
})
onUnmounted(() => {
  window.removeEventListener('online', updateOnline)
  window.removeEventListener('offline', updateOnline)
})
async function logout() {
  if (!window.dispatchEvent(new Event('tcg-before-logout', {cancelable:true}))) return
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
  <a class="skip" href="#content">{{ $t("본문 바로가기") }}</a>
  <header class="masthead" @keyup.esc="escapeMenu">
    <div class="shell masthead-inner">
      <RouterLink to="/" class="brand" :aria-label="$t('TCG 허브 홈')">
        <svg class="brand-mark" aria-hidden="true" viewBox="0 0 32 32" width="30" height="30"><rect x="1" y="1" width="30" height="30" rx="7" fill="currentColor"/><g fill="none" stroke="var(--sf)" stroke-width="1.7" stroke-linejoin="round"><path d="m8 9 10-2 3 15-10 2z"/><rect x="13" y="10" width="10" height="15" rx="1.4"/></g></svg><span>{{ $t("TCG 허브") }}</span>
      </RouterLink>
      <nav id="site-navigation" :aria-label="$t('주 메뉴')" :class="{'menu-open':menuOpen}">
        <RouterLink v-for="link in navigation" :key="link.to" :to="link.to"
          :class="{'current-section':link.pages.includes($route.name)}" @click="menuOpen=false">{{ t(link.label) }}</RouterLink>
        <a v-if="(session.isAdmin && session.adminMode !== 'DISABLED') || (!session.account && (session.adminMode === 'LOCAL_TOTP' || session.localEntryAlias))" href="/admin">{{ $t("관리자") }}</a>
      </nav>
      <div class="account-actions">
        <label class="locale-switch"><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/></svg><select :value="locale" :aria-label="$t('한국어 · English · 日本語')" @change="changeLanguage($event.target.value)"><option v-for="(name,code) in languages" :key="code" :value="code" :lang="code">{{ name }}</option></select></label>
        <button v-if="session.account" type="button" class="account-link" :disabled="busy" @click="logout">{{ $t("로그아웃") }}</button>
        <RouterLink v-else class="account-link" :to="loginTarget">{{ $t("로그인") }}</RouterLink>
        <button ref="menuButton" type="button" class="menu-switch" aria-controls="site-navigation"
          :aria-expanded="menuOpen" @click="menuOpen=!menuOpen">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path v-if="menuOpen" d="m5 5 14 14M19 5 5 19"/><path v-else d="M3 6h18M3 12h18M3 18h18"/>
          </svg>{{ $t("메뉴") }}
        </button>
      </div>
    </div>
    <DeckPageJump v-if="['decks','deck-new','deck-edit','shared-deck'].includes($route.name)" :menu-open="menuOpen"/>
  </header>
  <div v-if="!online" class="notice shell" role="status">{{ $t("오프라인입니다. 최근 열어 본 도감 페이지와 이미지를 조회할 수 있습니다.") }}</div>
  <div v-if="logoutError" class="notice shell" role="alert">{{ logoutError }}</div>
  <main id="content" class="shell" tabindex="-1"><RouterView /></main>
  <footer class="shell footer">{{ $t("카드 이름과 이미지의 권리는 각 권리자에게 있습니다.") }}</footer>
</template>
