// The previous PWA shell could open its cached login component through client-side navigation.
// Refresh only old, open app windows when an A90 localhost installation receives this update.
self.addEventListener('activate', event => {
  if (self.location.origin !== 'http://localhost:8080') return
  event.waitUntil(refreshOldLocalWindows().catch(() => {}))
})

async function refreshOldLocalWindows() {
  const response = await fetch('/api/v1/auth/admin-mode', {cache:'no-store', credentials:'omit'})
  if (!response.ok) return
  const info = await response.json()
  if (info.mode !== 'DISABLED' || info.localEntryAlias !== true) return
  const windows = await self.clients.matchAll({type:'window', includeUncontrolled:true})
  await Promise.allSettled(windows.map(async client => {
    const url = new URL(client.url)
    if (url.origin !== self.location.origin ||
        !/^\/(?:|cards(?:\/\d+)?|news|stores|play|binder|decks(?:\/new|\/\d+)?|login|admin|shared\/decks\/[\da-f-]+)\/?$/.test(url.pathname)) return
    const aware = await new Promise(resolve => {
      const channel = new MessageChannel()
      const timer = setTimeout(() => { channel.port1.close(); resolve(false) }, 600)
      channel.port1.onmessage = event => {
        clearTimeout(timer)
        channel.port1.close()
        resolve(event.data === true)
      }
      client.postMessage('tcg-local-entry-ready', [channel.port2])
    })
    // The resulting navigation may wait for activation to finish.
    if (!aware) client.navigate(url.href).catch(() => {})
  }))
}
