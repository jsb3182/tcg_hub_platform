import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory, START_LOCATION } from 'vue-router'
import { useSession } from './stores/session'
import App from './App.vue'
import CatalogView from './views/CatalogView.vue'
import './styles/tokens.css'
import './styles/app.css'
import './styles/operations.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', alias: '/cards', name: 'catalog', component: CatalogView, meta: { title: '카드 도감' } },
    { path: '/cards/:id(\\d+)', name: 'card', component: () => import('./views/CardView.vue'), meta: { title: '카드 상세' } },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { title: '로그인' } },
    { path: '/news', name: 'news', component: () => import('./views/NewsView.vue'), meta: { title: '새 소식' } },
    { path: '/stores', name: 'stores', component: () => import('./views/StoresView.vue'), meta: { title: '매장 지도' } },
    { path: '/binder', name: 'binder', component: () => import('./views/BinderView.vue'), meta: { title: '바인더' } },
    { path: '/decks', name: 'decks', component: () => import('./views/DecksView.vue'), meta: { title: '내 덱' } },
    { path: '/decks/new', name: 'deck-new', component: () => import('./views/DeckEditor.vue'), meta: { title: '덱 만들기' } },
    { path: '/decks/:id(\\d+)', name: 'deck-edit', component: () => import('./views/DeckEditor.vue'), meta: { title: '덱 편집' } },
    { path: '/shared/decks/:token', name: 'shared-deck', component: () => import('./views/SharedDeck.vue'), meta: { title: '공유 덱' } },
    { path: '/play', name: 'play', component: () => import('./views/PlayView.vue'), meta: { title: '플레이' } },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { title: '관리자' } },
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFound.vue'), meta: { title: '페이지를 찾을 수 없습니다' } },
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path !== from.path) return { top: 0 }
  },
})
const privateRoutes = new Set(['login','binder','decks','deck-new','deck-edit','admin'])
router.beforeEach(async (to, from) => {
  if (location.origin !== 'http://localhost:8080' ||
      !(privateRoutes.has(to.name) || (to.name === 'play' && to.query.deck))) return
  const session = useSession()
  try {
    await session.loadAdminMode()
    if (!session.localEntryAlias) return
  } catch {
    // Full document requests also run the server-side check. The first load has already done so.
    if (from === START_LOCATION) return
    location.assign(to.fullPath)
    return false
  }
  const entry = to.name === 'admin' ? '/login?next=/admin' :
    router.resolve({name:to.name,params:to.params,query:to.query,hash:to.hash}).fullPath
  location.replace('http://127.0.0.1:8080' + entry)
  return false
})
// An updated service worker only refreshes windows still running the previous alias-unaware bundle.
navigator.serviceWorker?.addEventListener('message', event => {
  if (event.data === 'tcg-local-entry-ready') event.ports[0]?.postMessage(true)
})
router.afterEach(to => { document.title = to.meta.title + ' · TCG 허브' })
createApp(App).use(createPinia()).use(router).mount('#app')
