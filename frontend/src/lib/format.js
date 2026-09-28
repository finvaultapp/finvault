import { t } from '../i18n'

const fmtCache = new Map()
let LOC = 'en-CA'

// Called by the i18n provider; fr-CA formats money as 1 234,56 $ and dates in French.
export function setFormatLocale(locale) {
  const next = locale === 'fr' ? 'fr-CA' : 'en-CA'
  if (next !== LOC) { LOC = next; fmtCache.clear() }
}

export const currentLocale = () => LOC

export function money(value, currency = 'CAD', { sign = false, compact = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const key = `${LOC}|${currency}|${compact}`
  let f = fmtCache.get(key)
  if (!f) {
    try {
      f = new Intl.NumberFormat(LOC, {
        style: 'currency', currency, currencyDisplay: 'narrowSymbol',
        notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 1 : 2, minimumFractionDigits: compact ? 0 : 2,
      })
    } catch {
      f = new Intl.NumberFormat(LOC, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    }
    fmtCache.set(key, f)
  }
  const out = f.format(Math.abs(value))
  if (value < 0) return `−${out}`
  return sign && value > 0 ? `+${out}` : out
}

export function date(iso, opts = { month: 'short', day: 'numeric', year: 'numeric' }) {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(LOC, opts)
}

export function monthLabel(ym) {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString(LOC, { month: 'long', year: 'numeric' })
}

export function shortMonth(ym) {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString(LOC, { month: 'short' })
}

export function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function addMonths(ym, n) {
  const [y, m] = ym.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function relativeDays(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  const diff = Math.round((new Date(y, m - 1, d) - new Date(new Date().toDateString())) / 86400000)
  if (diff === 0) return t('today')
  if (diff === 1) return t('tomorrow')
  if (diff === -1) return t('yesterday')
  return diff > 0 ? t('in {n} days', { n: diff }) : t('{n} days ago', { n: -diff })
}

// Labels are getters so they translate at read time (ACCOUNT_TYPES[k] and Object.entries both work).
export const ACCOUNT_TYPES = {
  get checking() { return t('Chequing') }, get savings() { return t('Savings') },
  get credit_card() { return t('Credit card') }, get investment() { return t('Investment') },
  get cash() { return t('Cash') }, get loan() { return t('Loan') }, get other() { return t('Other') },
}

export const CURRENCIES = ['CAD', 'USD', 'EUR', 'GBP', 'BRL', 'MXN', 'JPY', 'CHF', 'AUD', 'INR', 'CNY', 'HKD']

export function greeting(name) {
  const h = new Date().getHours()
  const first = name ? name.split(' ')[0] : ''
  if (h < 12) return first ? t('Good morning, {name}', { name: first }) : t('Good morning')
  if (h < 18) return first ? t('Good afternoon, {name}', { name: first }) : t('Good afternoon')
  return first ? t('Good evening, {name}', { name: first }) : t('Good evening')
}
