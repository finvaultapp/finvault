import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'
import { useI18n } from './i18n'

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

  useEffect(() => { document.documentElement.dataset.theme = theme; save('fv.theme', theme) }, [theme])
  useEffect(() => { document.documentElement.dataset.private = hidden; save('fv.private', hidden) }, [hidden])

  const refreshUser = useCallback(async () => {
    try {
      setStatus(await api.get('/auth/status'))
      const me = await api.get('/auth/me')
      if (me.locale) setLocale(me.locale)
      setUser(me)
    } catch {
      setUser(null)
    }
  }, [])

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
