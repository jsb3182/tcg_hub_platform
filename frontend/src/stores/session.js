import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '../api'

export const useSession = defineStore('session', () => {
  const account = ref(null)
  const ready = ref(false)
  const error = ref('')
  const isAdmin = computed(() => account.value?.role === 'ROLE_ADMIN')
  let initPromise
  let refreshPromise

  // Cross-tab requests share one rotating cookie, even though each tab has its own access token.
  function serialize(operation) {
    return navigator.locks ? navigator.locks.request('tcg-auth-cookie', operation) : operation()
  }
  function post(action, body) {
    return request('/auth/' + action, { method: 'POST', privateRequest: true, body })
  }
  function refresh() {
    if (!refreshPromise) {
      refreshPromise = serialize(async () => {
        try { account.value = await post('refresh') }
        catch (cause) {
          if (cause.status === 401 || cause.status === 403) account.value = null
          throw cause
        }
      }).finally(() => { refreshPromise = null })
    }
    return refreshPromise
  }
  function initialize() {
    if (!initPromise) {
      initPromise = refresh().catch(cause => {
        if (cause.status !== 401) error.value = cause.message
      }).finally(() => { ready.value = true })
    }
    return initPromise
  }
  async function login(email, password) {
    await initialize()
    await serialize(async () => { account.value = await post('login', { email, password }) })
    error.value = ''
  }
  async function logout() {
    await serialize(async () => {
      await post('logout')
      account.value = null
      error.value = ''
    })
  }
  async function adminStatus() {
    const load = () => request('/admin/status', { token: account.value?.accessToken, privateRequest: true })
    try { return await load() }
    catch (cause) {
      if (cause.status !== 401) throw cause
      await refresh()
      return load()
    }
  }
  return { account, ready, isAdmin, error, initialize, login, logout, adminStatus }
})
