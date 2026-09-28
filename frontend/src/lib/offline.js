// Page side of the installable app: service worker registration, wiping saved data on sign-out,
// the "showing saved data" state for the offline banner, and the install prompt for Settings.
// The worker itself is sw/sw.js; its caching rules are described there.
import { useSyncExternalStore } from 'react'

const API_CACHE = 'fv-api-v1' // same name as in sw/sw.js
const SESSION_KEY = '/__fv/session'
const MAX_AGE = 7 * 24 * 3600 * 1000 // same as the worker: saved data older than a week is not shown
const enabled = import.meta.env.PROD && typeof window !== 'undefined' && 'serviceWorker' in navigator && 'caches' in window

export function registerServiceWorker() {
  if (!enabled) return
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}) })
}

// Deletes every saved API response and the saved profile. Called whenever nobody is signed in.
export async function clearOfflineData() {
  setNet({ savedAt: null })
  if (!enabled) return
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    for (const w of [navigator.serviceWorker.controller, reg?.active]) w?.postMessage({ type: 'fv:clear-api' })
  } catch { /* no worker yet */ }
  try { await caches.delete(API_CACHE) } catch { /* storage blocked */ }
}

// The signed-in profile (never passwords or tokens; /api/auth responses are not cached by the worker) so
// the installed app can open offline and show whose saved data it is. Lives in the same cache as the API
// copies and is wiped with them.
export async function saveSession(user, status) {
  if (!enabled || !user) return
  try {
    const cache = await caches.open(API_CACHE)
    await cache.put(SESSION_KEY, new Response(JSON.stringify({ user, status, savedAt: Date.now() }), { headers: { 'Content-Type': 'application/json' } }))
  } catch { /* storage blocked */ }
}

export async function savedSession() {
  if (!enabled) return null
  try {
    const hit = await caches.match(SESSION_KEY, { cacheName: API_CACHE })
    const snap = hit && await hit.json()
    return snap?.user && Date.now() - snap.savedAt < MAX_AGE ? snap : null
  } catch { return null }
}

// --- "Offline, showing saved data from {time}" -----------------------------------------------------
let net = { savedAt: null } // ISO time of the oldest saved copy on screen, or null when data is live
const subscribers = new Set()
function setNet(next) {
  if (next.savedAt === net.savedAt) return
  net = next
  subscribers.forEach((fn) => fn())
}

// Called by api.js for every response.
export function noteResponse(res) {
  if (res.headers.get('X-FinVault-From-Cache')) {
    const at = res.headers.get('X-FinVault-Saved-At')
    if (at && (!net.savedAt || at < net.savedAt)) setNet({ savedAt: at })
  } else if (net.savedAt && res.ok) {
    setNet({ savedAt: null })
  }
}

export const useSavedDataTime = () => useSyncExternalStore((fn) => { subscribers.add(fn); return () => subscribers.delete(fn) }, () => net.savedAt)

// --- Install hint -------------------------------------------------------------------------------------
let deferredPrompt = null
const installSubs = new Set()
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault() // keep it for the button in Settings instead of the browser's mini-infobar
    deferredPrompt = e
    installSubs.forEach((fn) => fn())
  })
  window.addEventListener('appinstalled', () => { deferredPrompt = null; installSubs.forEach((fn) => fn()) })
}

export const useInstallPrompt = () => useSyncExternalStore((fn) => { installSubs.add(fn); return () => installSubs.delete(fn) }, () => deferredPrompt)

export async function promptInstall() {
  const p = deferredPrompt
  if (!p) return false
  deferredPrompt = null
  installSubs.forEach((fn) => fn())
  p.prompt()
  const choice = await p.userChoice.catch(() => null)
  return choice?.outcome === 'accepted'
}

export const isStandalone = () => window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true
export const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
