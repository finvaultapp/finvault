import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { money } from '../lib/format'
import { t } from '../i18n'
import { categoryIcon } from '../lib/categoryIcon'

// ---- Toasts ---------------------------------------------------------------
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, kind = 'ok') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, kind }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 3500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((x) => (
          <div key={x.id} className={`toast ${x.kind}`}>
            {x.kind === 'error' ? <AlertTriangle /> : <CheckCircle2 />}
            <span>{x.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// ---- Money ------------------------------------------------------------------
export function Money({ value, currency, sign, colored, compact, className = '' }) {
  const tone = colored && value ? (value > 0 ? 'income' : 'expense') : ''
  return <span className={`money money-v ${tone} ${className}`}>{money(value, currency, { sign, compact })}</span>
}

// ---- Dialog -----------------------------------------------------------------
export function Dialog({ title, onClose, children, footer, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const first = ref.current?.querySelector('input, select, textarea, button:not(.icon-btn)')
    first?.focus()
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.() }
  }, [onClose])
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <div className="dialog-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={t('Close')}><X /></button>
        </div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>
  )
}

export function Confirm({ title, body, action, danger = true, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false)
  return (
    <Dialog title={title} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className={`btn ${danger ? 'danger' : 'primary'}`} disabled={busy}
        onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false) } onClose() }}>
        {busy && <Loader2 className="spin" />}{action ?? t('Delete')}
      </button>
    </>}>
      <p className="muted">{body}</p>
    </Dialog>
  )
}

// ---- Bits -------------------------------------------------------------------
export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}

export function Switch({ checked, onChange, label }) {
  return (
    <label className="switch" aria-label={label}>
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span />
    </label>
  )
}

export function CategoryTile({ name, color, size }) {
  const Icon = categoryIcon(name)
  return <span className={`tile ${size === 'sm' ? 'sm' : ''}`} style={{ '--tile': color || '#94A3B8' }}><Icon /></span>
}

export function Progress({ value, color, thick }) {
  const pct = Math.max(0, Math.min(100, value ?? 0))
  return <div className={`progress ${thick ? 'thick' : ''}`}><span style={{ width: `${pct}%`, '--bar': color }} /></div>
}

export function Empty({ icon: Icon = Info, title, children, action }) {
  return (
    <div className="empty">
      <span className="tile"><Icon /></span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Warnings({ items }) {
  if (!items?.length) return null
  return (
    <div className="banner warn" role="alert">
      <AlertTriangle />
      <div className="banner-body">
        <strong>{t("Some amounts aren't in your totals.")}</strong>{' '}
        {items.length === 1
          ? t('{pairs} has no exchange rate yet.', { pairs: items.map((w) => w.pair).join(', ') })
          : t('{pairs} have no exchange rate yet.', { pairs: items.map((w) => w.pair).join(', ') })}{' '}
        <Link to="/settings#currency">{t('Add a rate')}</Link> {t('to include them.')}
      </div>
    </div>
  )
}

export function Loading({ rows = 4 }) {
  return (
    <div className="card card-body stack" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height: 18, width: `${90 - i * 12}%` }} />)}
    </div>
  )
}

export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  )
}

// Data fetching hook with reload.
export function useData(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    loader().then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (error) => alive && setState({ data: null, error, loading: false }),
    )
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((n) => n + 1) }
}

export function ErrorNote({ error }) {
  if (!error) return null
  return <div className="banner warn"><AlertTriangle /><div className="banner-body">{error.message}</div></div>
}
