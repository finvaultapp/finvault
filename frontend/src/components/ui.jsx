import { Children, cloneElement, createContext, isValidElement, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { money } from '../lib/format'
import { t } from '../i18n'
import { categoryIcon } from '../lib/categoryIcon'

// ---- Toasts and screen-reader announcements ---------------------------------
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)
const AnnounceCtx = createContext(() => {})
// Says something to screen readers without showing a toast (a sorted line, a finished step).
export const useAnnounce = () => useContext(AnnounceCtx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const [said, setSaid] = useState('')
  const push = useCallback((message, kind = 'ok') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, kind }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 3500)
  }, [])
  const announce = useCallback((message) => {
    setSaid('') // clear first so the same words are read again
    setTimeout(() => setSaid(message), 60)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      <AnnounceCtx.Provider value={announce}>
        {children}
        <div className="toasts" role="status" aria-live="polite">
          {items.map((x) => (
            <div key={x.id} className={`toast ${x.kind}`}>
              {x.kind === 'error' ? <AlertTriangle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
              <span>{x.kind === 'error' && <span className="sr">{t('Error:')} </span>}{x.message}</span>
            </div>
          ))}
        </div>
        <div className="sr" role="status" aria-live="polite">{said}</div>
      </AnnounceCtx.Provider>
    </ToastCtx.Provider>
  )
}

// Scripted scrolling follows the reduced-motion setting too (CSS handles the rest).
export const reducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Enter or Space on a role="button" element that isn't a <button> (the dropzones). Space mustn't scroll the page.
export const activateOnKey = (fn) => (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn() }
}

// ---- Modal focus --------------------------------------------------------------
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
const layers = [] // open modal layers, topmost last; only the top one answers Escape and Tab

// Moves focus into a modal layer, keeps Tab inside it, closes on Escape, and gives focus back when it closes.
export function useModal(ref, onClose, pickFirst) {
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const el = ref.current
    const prev = document.activeElement
    const layer = {}
    layers.push(layer)
    const first = pickFirst?.(el) ?? el?.querySelector('input:not([type="hidden"]), select, textarea, button:not(.icon-btn)') ?? el
    first?.focus()
    const onKey = (e) => {
      if (layers[layers.length - 1] !== layer || !el) return
      if (e.key === 'Escape') { e.preventDefault(); close.current() }
      else if (e.key === 'Tab') {
        const items = [...el.querySelectorAll(FOCUSABLE)].filter((x) => x.getClientRects().length)
        if (!items.length) { e.preventDefault(); return }
        const a = items[0]
        const z = items[items.length - 1]
        const inside = el.contains(document.activeElement)
        if (e.shiftKey && (document.activeElement === a || !inside)) { e.preventDefault(); z.focus() }
        else if (!e.shiftKey && (document.activeElement === z || !inside)) { e.preventDefault(); a.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      layers.splice(layers.indexOf(layer), 1)
      // Back to what opened it; if that is gone (a deleted row), to the main content.
      const back = prev?.isConnected && prev !== document.body ? prev : document.getElementById('main')
      back?.focus?.({ preventScroll: true })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}

// ---- Money ------------------------------------------------------------------
export function Money({ value, currency, sign, colored, compact, className = '' }) {
  const tone = colored && value ? (value > 0 ? 'income' : 'expense') : ''
  return <span className={`money money-v ${tone} ${className}`}>{money(value, currency, { sign, compact })}</span>
}

// ---- Dialog -----------------------------------------------------------------
export function Dialog({ title, onClose, children, footer, wide }) {
  const ref = useRef(null)
  const titleId = useId()
  useModal(ref, onClose)
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref} tabIndex={-1}>
        <div className="dialog-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={t('Close')}><X aria-hidden="true" /></button>
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
// A labelled control. A single native input, select or textarea child (or a component marked `field`) gets its
// hint and error tied on with aria-describedby, aria-invalid when there is an error, and a mark when required.
// `group` is for composite controls such as the tag input: a div labels it, so clicks on its chips stay chips.
export function Field({ label, hint, error, group, children, className = '' }) {
  const id = useId()
  const child = Children.count(children) === 1 && isValidElement(children) ? children : null
  const wired = child && (typeof child.type === 'string' ? /^(input|select|textarea)$/.test(child.type) : child.type.field)
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [child?.props['aria-describedby'], hintId, errorId].filter(Boolean).join(' ') || undefined
  const required = child?.props.required
  const mark = required && <span className="req" aria-hidden="true"> *</span>
  const extra = (
    <>
      {hint && <small id={hintId}>{hint}</small>}
      {error && <small id={errorId} className="field-error" role="alert">{error}</small>}
    </>
  )
  if (group && child) {
    return (
      <div className={`field ${className}`} role="group" aria-labelledby={`${id}-label`}>
        <span id={`${id}-label`}>{label}</span>
        {cloneElement(child, { labelledBy: `${id}-label`, describedBy })}
        {extra}
      </div>
    )
  }
  if (wired) {
    const controlId = child.props.id ?? `${id}-control`
    return (
      <div className={`field ${className}`}>
        <label htmlFor={controlId} className="field-label">{label}{mark}</label>
        {cloneElement(child, { id: controlId, 'aria-describedby': describedBy, 'aria-invalid': error ? true : child.props['aria-invalid'] })}
        {extra}
      </div>
    )
  }
  return (
    <label className={`field ${className}`}>
      <span>{label}{mark}</span>
      {children}
      {extra}
    </label>
  )
}

export function Switch({ checked, onChange, label }) {
  return (
    <label className="switch">
      <input type="checkbox" role="switch" checked={!!checked} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <span aria-hidden="true" />
    </label>
  )
}

// The pigeonhole tab label in miniature: a full-round pill in the category's tint with a dot and a small icon.
// `label` (optional) prints text inside the pill; `icon` (optional) overrides the icon guessed from the name.
export function CategoryTile({ name, color, size, label, icon }) {
  const Icon = icon ?? categoryIcon(name)
  return (
    <span className={`cat-tab ${size === 'sm' ? 'sm' : ''}`} style={color ? { '--c': color } : undefined} title={label ? undefined : name || undefined}>
      <i aria-hidden="true" /><Icon aria-hidden="true" />{label && <b>{label}</b>}
    </span>
  )
}

export function Progress({ value, color, thick }) {
  const pct = Math.max(0, Math.min(100, value ?? 0))
  return <div className={`progress ${thick ? 'thick' : ''}`}><span style={{ width: `${pct}%`, '--bar': color }} /></div>
}

export function Empty({ icon: Icon = Info, title, children, action }) {
  return (
    <div className="empty">
      <Icon className="empty-icon" aria-hidden="true" />
      <h2>{title}</h2>
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
      <span className="sr" role="status">{t('Loading…')}</span>
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height: 18, width: `${90 - i * 12}%` }} />)}
    </div>
  )
}

export function PageHead({ title, sub, children }) {
  usePageTitle(title)
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

// The browser tab names the page, so screen readers and history say where you are.
export function usePageTitle(title) {
  useEffect(() => {
    if (typeof title === 'string' && title) document.title = `${title} · FinVault`
  }, [title])
}

// The numbers behind a chart, as a table anyone can open: for screen readers, keyboard users and people who
// can't tell the colours apart. `columns` are header labels; `rows` are arrays of cells (text or elements).
export function ChartTable({ caption, columns, rows }) {
  if (!rows?.length) return null
  return (
    <details className="chart-table">
      <summary>{t('Show as a table')}</summary>
      <div className="table-wrap" tabIndex={0} role="region" aria-label={caption}>
        <table className="table">
          <caption className="sr">{caption}</caption>
          <thead><tr>{columns.map((c, i) => <th key={i} scope="col" className={i ? 'amount' : undefined}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{r.map((cell, j) => (j === 0 ? <th key={j} scope="row">{cell}</th> : <td key={j} className="amount">{cell}</td>))}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
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
