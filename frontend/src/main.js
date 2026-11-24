import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import CatalogView from './views/CatalogView.vue'
import './styles/tokens.css'
import './styles/app.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', alias: '/cards', name: 'catalog', component: CatalogView, meta: { title: '카드 도감' } },
    { path: '/cards/:id(\\d+)', name: 'card', component: () => import('./views/CardView.vue'), meta: { title: '카드 상세' } },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { title: '로그인' } },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { title: '관리자' } },
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFound.vue'), meta: { title: '페이지를 찾을 수 없습니다' } },
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path !== from.path) return { top: 0 }
  },
})
router.afterEach(to => { document.title = to.meta.title + ' · TCG 허브' })
createApp(App).use(createPinia()).use(router).mount('#app')
