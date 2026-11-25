import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, request } from '../api'

export const useSession = defineStore('session', () => {
  const account = ref(null)
  const ready = ref(false)
  const error = ref('')
  const adminAccessBlocked = ref(false)
  const adminMode = ref(null)
  const localEntryAlias = ref(false)
  const isAdmin = computed(() => account.value?.role === 'ROLE_ADMIN')
  let initPromise
  let refreshPromise
  let modePromise

  function loadAdminMode() {
    if (adminMode.value) return Promise.resolve(adminMode.value)
    if (!modePromise) {
      modePromise = request('/auth/admin-mode', { privateRequest: true }).then(({ mode, localEntryAlias: alias }) => {
        if (!['LOCAL_TOTP', 'CLOUDFLARE', 'DISABLED'].includes(mode)) throw new ApiError(502)
        localEntryAlias.value = alias === true && mode === 'DISABLED'
        adminMode.value = mode
        return mode
      }).finally(() => { modePromise = null })
    }
    return modePromise
  }

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
      initPromise = (async () => {
        if (location.origin === 'http://localhost:8080') {
          await loadAdminMode().catch(() => {})
          if (localEntryAlias.value) return
        }
        await refresh()
      })().catch(cause => {
        if (cause.status !== 401) error.value = cause.message
      }).finally(() => { ready.value = true })
    }
    return initPromise
  }
  async function login(email, password) {
    await initialize()
    await serialize(async () => { account.value = await post('login', { email, password }) })
    adminAccessBlocked.value = false
    error.value = ''
  }
  async function logout() {
    await serialize(async () => {
      await post('logout')
      account.value = null
      adminAccessBlocked.value = false
      error.value = ''
    })
  }
  async function authenticatedRequest(path, options) {
    const load = () => request(path, { ...options, token: account.value?.accessToken, privateRequest: true })
    try { return await load() }
    catch (cause) { if (cause.status !== 401) throw cause }
    await refresh()
    return load()
  }
  async function adminRequest(path, options = {}) {
    try {
      return await authenticatedRequest('/admin' + path, options)
    } catch (cause) {
      if (isAdmin.value && [401, 403].includes(cause.status)) adminAccessBlocked.value = true
      throw cause
    }
  }
  function verifyLocalCode(code, signal) {
    return authenticatedRequest('/auth/local-admin', { method: 'POST', body: { code }, signal })
  }
  return { account, ready, isAdmin, adminAccessBlocked, adminMode, localEntryAlias, error, initialize, login, logout,
    loadAdminMode, authenticatedRequest, adminRequest, verifyLocalCode }
})
