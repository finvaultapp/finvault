import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'
import { clearOfflineData, savedSession, saveSession } from './lib/offline'

const AppCtx = createContext(null)
export const useApp = () => useContext(AppCtx)

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback } catch { return fallback }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode */ }
}

export function AppProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = loading, null = signed out
  const [status, setStatus] = useState(null)
  const [version, setVersion] = useState(0) // bump to refresh sidebar and dashboards after writes
  const [theme, setTheme] = useState(() => load('fv.theme', window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  const [hidden, setHidden] = useState(() => load('fv.private', false))
  const { setLocale } = useI18n()
  const offlineUser = useRef(null)

  useEffect(() => { document.documentElement.dataset.theme = theme; save('fv.theme', theme) }, [theme])
  useEffect(() => { document.documentElement.dataset.private = hidden; save('fv.private', hidden) }, [hidden])

  const refreshUser = useCallback(async () => {
    try {
      const st = await api.get('/auth/status')
      setStatus(st)
      const me = await api.get('/auth/me')
      if (me.locale) setLocale(me.locale)
      setUser(me)
    } catch (err) {
      // No network: the installed app opens on the data saved on this device, if someone is signed in.
      const saved = err?.status === 0 ? await savedSession() : null
      if (saved) { setStatus(saved.status); if (saved.user.locale) setLocale(saved.user.locale) }
      offlineUser.current = saved?.user ?? null
      setUser(saved ? saved.user : null)
    }
  }, [])

  // Nobody signed in (sign-out, "sign out everywhere", an expired session): wipe data saved for offline use.
  useEffect(() => { if (user === null) clearOfflineData() }, [user])
  // Keep the saved profile current, but never re-save the one the app opened offline with.
  useEffect(() => { if (user && user !== offlineUser.current) saveSession(user, status) }, [user, status])

  useEffect(() => {
    refreshUser()
    const onOut = () => setUser(null)
    window.addEventListener('fv:signed-out', onOut)
    return () => window.removeEventListener('fv:signed-out', onOut)
  }, [refreshUser])

  const value = {
    user, setUser, status, refreshUser, version, bump: () => setVersion((v) => v + 1),
    theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    hidden, toggleHidden: () => setHidden((h) => !h),
  }
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}
