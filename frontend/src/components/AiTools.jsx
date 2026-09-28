// AI helpers for sorting and search. Everything here renders nothing unless the member's AI is ready
// (a model is set up and they opted in), matching the chat page.
import { useEffect, useState } from 'react'
import { Check, Sparkles, X } from 'lucide-react'
import { api, qs } from '../api'
import { t } from '../i18n'

export function useAiReady() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let alive = true
    api.get('/ai/status').then((s) => alive && setReady(Boolean(s?.ready)), () => {})
    return () => { alive = false }
  }, [])
  return ready
}

const byTx = (list) => Object.fromEntries((list ?? []).map((s) => [s.transaction_id, s]))

// Suggestions for a set of uncategorized transactions. Loading shows cached answers only;
// ask() is the one call that may send descriptions to the model.
export function useAiSuggestions(txIds, ready) {
  const key = txIds.join(',')
  const [map, setMap] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [asked, setAsked] = useState(null)
  const [unasked, setUnasked] = useState(0)

  useEffect(() => {
    setAsked(null); setError(null)
    if (!ready || !txIds.length) { setMap({}); setUnasked(0); return undefined }
    let alive = true
    api.get(`/ai/suggestions${qs({ transaction_id: txIds })}`).then((r) => {
      if (alive) { setMap(byTx(r.suggestions)); setUnasked(r.unasked) }
    }, () => {})
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, key])

  const ask = async () => {
    setBusy(true); setError(null)
    try {
      const r = await api.post('/ai/suggestions', { transaction_ids: txIds })
      setMap(byTx(r.suggestions)); setUnasked(r.unasked); setAsked(r)
    } catch (e) { setError(e) }
    setBusy(false)
  }
  const accept = (items, createRules = false) => api.post('/ai/suggestions/accept', {
    items: items.map((s) => ({ transaction_id: s.transaction_id, category_id: s.category_id })), create_rules: createRules,
  })
  const reject = async (s) => {
    await api.post('/ai/suggestions/reject', { transaction_ids: [s.transaction_id] })
    setMap((m) => Object.fromEntries(Object.entries(m).filter(([, v]) => v.merchant !== s.merchant)))
  }
  // missing: merchants on screen that rules, history and the cache can't answer, so asking would send them.
  return { map, list: Object.values(map), ask, busy, error, asked, accept, reject, missing: unasked }
}

export function AiChip({ s, onAccept, onReject }) {
  return (
    <span className="ai-chip" style={{ '--c': s.category_color }}>
      <button type="button" className="ai-chip-main" onClick={onAccept}
        title={t('Accept this suggestion ({pct}% sure)', { pct: Math.round(s.confidence * 100) })}>
        <Sparkles aria-hidden="true" /><span className="ai-chip-lead">{t('AI suggests:')}</span> {s.category_name}
      </button>
      {onReject && <button type="button" className="ai-chip-x" onClick={onReject} aria-label={t('Reject suggestion')}><X /></button>}
    </span>
  )
}

// Bar over the uncategorized list: ask for suggestions, then accept them all at once.
export function AiSuggestBar({ ai, onAcceptAll }) {
  const [rules, setRules] = useState(false)
  const [saving, setSaving] = useState(false)
  const n = ai.list.length
  if (n === 0 && ai.missing === 0 && !ai.error && !ai.asked) return null
  const acceptAll = async () => {
    setSaving(true)
    try { await onAcceptAll(ai.list, rules) } finally { setSaving(false) }
  }
  return (
    <div className="banner ca ai-bar">
      <Sparkles />
      <div className="banner-body">
        {n > 0
          ? <strong>{n === 1 ? t('1 AI suggestion on this page.') : t('{n} AI suggestions on this page.', { n })}</strong>
          : <strong>{t('Let AI suggest categories for unfamiliar merchants.')}</strong>}{' '}
        <span className="small">{t('Only descriptions, amounts and your category names are sent. Nothing changes until you accept.')}</span>
        {ai.asked && ai.asked.sent === 0 && n === 0 && <div className="small">{t('No new merchants to ask about. Rules and past choices already cover the rest.')}</div>}
        {ai.error && <div className="small expense">{ai.error.message}</div>}
      </div>
      {n > 0 && <label className="check small"><input type="checkbox" checked={rules} onChange={(e) => setRules(e.target.checked)} />{t('Also create rules')}</label>}
      {ai.missing > 0 && <button className="btn sm" onClick={ai.ask} disabled={ai.busy}><Sparkles />{ai.busy ? t('Asking…') : t('Suggest with AI')}</button>}
      {n > 0 && <button className="btn sm primary" onClick={acceptAll} disabled={saving}><Check />{t('Accept all {n}', { n })}</button>}
    </div>
  )
}

// Plain-language search box. Returns the interpreted filters to the page, which applies them as normal URL filters.
export function AskBox({ onResult }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    if (question.trim().length < 2) return
    setBusy(true); setError(null)
    try { onResult(await api.post('/ai/search', { question: question.trim() })) } catch (err) { setError(err) }
    setBusy(false)
  }
  return (
    <form className="ask-box" onSubmit={submit}>
      <div className="search-box">
        <Sparkles />
        <input className="input" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} autoFocus
          placeholder={t('e.g. restaurants over $50 last spring')} aria-label={t('Ask in plain words')} />
      </div>
      <button className="btn primary" type="submit" disabled={busy || question.trim().length < 2}>{busy ? t('Reading…') : t('Search')}</button>
      {error && <div className="ask-error small expense" role="alert">{error.message}</div>}
    </form>
  )
}

// Filters from /ai/search -> the Transactions page's URL params (the same ones the filter panel sets).
export function aiFiltersToParams(f) {
  const p = new URLSearchParams()
  if (f.start) p.set('start', f.start)
  if (f.end) p.set('end', f.end)
  f.category_id?.forEach((id) => p.append('category', id))
  f.account_id?.forEach((id) => p.append('account', id))
  if (f.min_amount != null) p.set('min', f.min_amount)
  if (f.max_amount != null) p.set('max', f.max_amount)
  if (f.kind) p.set('kind', f.kind)
  if (f.q) p.set('q', f.q)
  return p
}
