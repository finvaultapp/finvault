// Tiny i18n: the English text is the key; French comes from the dictionaries in ./locales/fr.
// t('Hello {name}', { name }) fills {placeholders}. Missing French falls back to English.
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { setFormatLocale } from './lib/format'

const modules = import.meta.glob('./locales/fr/*.js', { eager: true })
const FR = Object.assign({}, ...Object.values(modules).map((m) => m.default))

export const LANGUAGES = { en: 'English', fr: 'Français' }

let current = 'en'

function fill(text, vars) {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? `{${k}}`))
}

// Usable outside React (helpers, constants evaluated at render time).
export function t(text, vars) {
  const out = current === 'fr' ? FR[text] ?? text : text
  return fill(out, vars)
}

export function detectLocale() {
  try {
    const saved = localStorage.getItem('fv.locale')
    if (saved) return JSON.parse(saved)
  } catch { /* private mode */ }
  return (navigator.language || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en'
}

const Ctx = createContext({ locale: 'en', setLocale: () => {}, t })
export const useI18n = () => useContext(Ctx)

export function I18nProvider({ initial, children }) {
  const [locale, setLocale] = useState(initial || detectLocale())
  current = locale
  setFormatLocale(locale)
  useEffect(() => {
    document.documentElement.lang = locale === 'fr' ? 'fr-CA' : 'en-CA'
    try { localStorage.setItem('fv.locale', JSON.stringify(locale)) } catch { /* ignore */ }
  }, [locale])
  const value = useMemo(() => ({ locale, setLocale, t }), [locale])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
