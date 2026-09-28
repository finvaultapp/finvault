/* FinVault service worker (hand-written, no libraries). Built into /sw.js by sw/plugin.js, which fills in
 * VERSION and PRECACHE. Registered only in production builds (src/lib/offline.js).
 *
 * What it does
 * - App shell: index.html and the built JS/CSS are precached per version (fv-shell-<version>); fonts and
 *   icons are cached on first use. Old shell caches are deleted when a new version activates.
 * - GET /api/* on the OFFLINE_API list: network first. A good JSON response is copied into fv-api-v1 with
 *   the time it was saved; if the network fails (or takes longer than 8 s) the saved copy is returned,
 *   marked with X-FinVault-From-Cache so the app can say "Offline, showing saved data from …".
 * - Everything else goes straight to the network and is never stored: writes (POST/PUT/PATCH/DELETE are
 *   not even intercepted, so they fail loudly offline instead of being queued), /api/auth/*, admin, AI,
 *   imports, attachment files, exports, and any request made with cache: 'no-store'.
 * - Saved API data is deleted on sign-out (the app posts {type: 'fv:clear-api'}), whenever the server
 *   answers 401, and is never served when older than MAX_AGE.
 *
 * About Cache-Control: no-store on /api: the backend keeps sending it, so the browser's HTTP cache and
 * any proxy never keep a copy of financial data (we can't wipe those on sign-out). This worker's cache is
 * different: it is explicit, limited to the read-only views above, and wiped on sign-out and on 401.
 * The Cache API does not apply HTTP caching rules, so this is a deliberate, scoped exception.
 */
const VERSION = '__FV_VERSION__'
const PRECACHE = [/* __FV_PRECACHE__ */]
const SHELL = `fv-shell-${VERSION}`
const API = 'fv-api-v1'
const SAVED_AT = 'X-FinVault-Saved-At'
const FROM_CACHE = 'X-FinVault-From-Cache'
const NETWORK_TIMEOUT = 8000
const MAX_AGE = 7 * 24 * 3600 * 1000

// Read-only views that may be shown offline.
const OFFLINE_API = [
  /^\/api\/accounts$/, /^\/api\/transactions$/, /^\/api\/transactions\/\d+\/detail$/, /^\/api\/budgets$/,
  /^\/api\/categories$/, /^\/api\/rules$/, /^\/api\/reports\/(dashboard|income-expense|net-worth)$/,
  /^\/api\/goals$/, /^\/api\/recurring$/, /^\/api\/assets$/, /^\/api\/plans$/, /^\/api\/tax\/summary$/,
  /^\/api\/bills\/calendar$/, /^\/api\/people$/, /^\/api\/sync\/status$/, /^\/api\/currency\/(status|rates)$/,
]
// Must always be fresh or must never sit on the device, even if a pattern above would match.
const NEVER = /^\/api\/(auth|admin|ai|imports|inbox|attachments)(\/|$)|\/(export|attachments|file)(\/|$)/

let generation = 0 // bumped on every wipe so a response already in flight can't be saved afterwards

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL)
    await cache.addAll(PRECACHE.map((url) => new Request(url, { cache: 'reload' })))
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if ((key.startsWith('fv-shell-') && key !== SHELL) || (key.startsWith('fv-api-') && key !== API)) await caches.delete(key)
    }
    await self.clients.claim()
  })())
})

self.addEventListener('message', (event) => {
  if (event.data?.type !== 'fv:clear-api') return
  generation++
  event.waitUntil(caches.delete(API).then(() => event.ports?.[0]?.postMessage('cleared')))
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin || url.pathname === '/sw.js') return
  if (url.pathname.startsWith('/api/')) {
    if (req.cache !== 'no-store' && !NEVER.test(url.pathname) && OFFLINE_API.some((re) => re.test(url.pathname))) {
      event.respondWith(networkFirst(req))
    }
    return
  }
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(async () => (await caches.match('/', { cacheName: SHELL })) || Response.error()))
    return
  }
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || PRECACHE.includes(url.pathname)) {
    event.respondWith(cacheFirst(req))
  }
})

async function cacheFirst(req) {
  const hit = await caches.match(req, { cacheName: SHELL })
  if (hit) return hit
  const res = await fetch(req)
  if (res.ok && res.type === 'basic') {
    const copy = res.clone()
    caches.open(SHELL).then((c) => c.put(req, copy)).catch(() => {})
  }
  return res
}

async function networkFirst(req) {
  const gen = generation
  const network = fetch(req).then(async (res) => {
    if (res.status === 401) {
      generation++
      await caches.delete(API)
    } else if (res.ok && res.type === 'basic' && (res.headers.get('Content-Type') || '').includes('application/json')) {
      const headers = new Headers(res.headers)
      headers.set(SAVED_AT, new Date().toISOString())
      const body = await res.clone().arrayBuffer()
      if (gen === generation) {
        const cache = await caches.open(API)
        if (gen === generation) await cache.put(req, new Response(body, { status: res.status, statusText: res.statusText, headers }))
      }
    }
    return res
  })
  network.catch(() => {}) // handled below; avoids an unhandled rejection when the timeout wins
  try {
    return await Promise.race([network, new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), NETWORK_TIMEOUT))])
  } catch {
    const saved = await fromCache(req)
    return saved || network.catch(() => Response.error())
  }
}

async function fromCache(req) {
  const hit = await caches.match(req, { cacheName: API, ignoreVary: true })
  if (!hit) return null
  const savedAt = Date.parse(hit.headers.get(SAVED_AT) || '')
  if (!(Date.now() - savedAt < MAX_AGE)) return null
  const headers = new Headers(hit.headers)
  headers.set(FROM_CACHE, '1')
  return new Response(await hit.arrayBuffer(), { status: hit.status, statusText: hit.statusText, headers })
}
