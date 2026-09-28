import { useRef, useState } from 'react'
import { FileText, Paperclip, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api } from '../api'
import { t } from '../i18n'
import { Dialog, Field, Money, useData, useToast } from './ui'
import { todayISO } from '../lib/format'
import { TAX_TAGS } from '../lib/tax'

export function CategorySelect({ categories, value, onChange, className = 'input', placeholder, ...rest }) {
  const groups = { expense: t('Expenses'), income: t('Income'), transfer: t('Transfers') }
  return (
    <select className={className} value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} {...rest}>
      <option value="">{placeholder ?? t('Uncategorized')}</option>
      {Object.entries(groups).map(([k, label]) => (
        <optgroup key={k} label={label}>
          {categories.filter((c) => c.kind === k).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </optgroup>
      ))}
    </select>
  )
}

export default function TxDialog({ tx, accounts, categories, onClose, onSaved, initialTab = 'details' }) {
  const editing = !!tx?.id
  const [tab, setTab] = useState(editing ? initialTab : 'details')
  const tabs = editing
    ? [['details', t('Details')], ['split', t('Split')], ...(tx.amount < 0 ? [['share', t('Share')]] : []), ['receipts', t('Receipts')]]
    : [['details', t('Details')]]
  return (
    <Dialog wide={tab !== 'details'} title={editing ? t('Edit transaction') : t('Add transaction')} onClose={onClose}>
      {editing && (
        <div className="segmented" style={{ marginBottom: 16 }} role="tablist">
          {tabs.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>)}
        </div>
      )}
      {tab === 'details' && <Details tx={tx} accounts={accounts} categories={categories} onClose={onClose} onSaved={onSaved} />}
      {tab === 'split' && <SplitEditor tx={tx} categories={categories} onSaved={onSaved} />}
      {tab === 'share' && <ShareEditor tx={tx} onSaved={onSaved} />}
      {tab === 'receipts' && <Receipts tx={tx} onSaved={onSaved} />}
    </Dialog>
  )
}

function Details({ tx, accounts, categories, onClose, onSaved }) {
  const toast = useToast()
  const editing = !!tx?.id
  const [f, setF] = useState(() => ({
    account_id: tx?.account_id ?? accounts[0]?.id, date: tx?.date ?? todayISO(),
    kind: tx && tx.amount > 0 ? 'in' : 'out', amount: tx ? Math.abs(tx.amount) : '',
    description: tx?.description ?? '', payee: tx?.payee ?? '', notes: tx?.notes ?? '', category_id: tx?.category_id ?? null,
    tax_tag: tx?.tax_tag ?? '',
  }))
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const tags = TAX_TAGS()

  const save = async (e) => {
    e?.preventDefault()
    setBusy(true)
    const body = { account_id: Number(f.account_id), date: f.date, amount: (f.kind === 'out' ? -1 : 1) * Number(f.amount),
      description: f.description, payee: f.payee, notes: f.notes, category_id: f.category_id }
    try {
      const saved = editing ? await api.patch(`/transactions/${tx.id}`, body) : await api.post('/transactions', body)
      if ((f.tax_tag || null) !== (tx?.tax_tag ?? null)) await api.put(`/transactions/${saved.id}/tax-tag`, { tax_tag: f.tax_tag || null })
      toast(editing ? t('Transaction updated') : t('Transaction added'))
      onSaved()
      onClose()
    } catch (err) { toast(err.message, 'error') }
    setBusy(false)
  }

  return (
    <>
      <form className="form-grid" onSubmit={save}>
        <div className="full segmented" style={{ width: 'fit-content' }}>
          <button type="button" className={f.kind === 'out' ? 'on' : ''} onClick={() => setF({ ...f, kind: 'out' })}>{t('Money out')}</button>
          <button type="button" className={f.kind === 'in' ? 'on' : ''} onClick={() => setF({ ...f, kind: 'in' })}>{t('Money in')}</button>
        </div>
        <Field label={t('Amount')}><input className="input" type="number" step="0.01" min="0" required value={f.amount} onChange={set('amount')} /></Field>
        <Field label={t('Date')}><input className="input" type="date" required value={f.date} onChange={set('date')} /></Field>
        <Field label={t('Description')} className="full"><input className="input" required value={f.description} onChange={set('description')} /></Field>
        <Field label={t('Account')}>
          <select className="input" value={f.account_id} onChange={set('account_id')}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>)}
          </select>
        </Field>
        <Field label={t('Category')}><CategorySelect categories={categories} value={f.category_id} onChange={(v) => setF({ ...f, category_id: v })} /></Field>
        <Field label={t('Payee')} hint={t('Optional clean name, e.g. “Loblaws”.')}><input className="input" value={f.payee} onChange={set('payee')} /></Field>
        <Field label={t('Notes')}><input className="input" value={f.notes} onChange={set('notes')} /></Field>
        <Field label={t('Tax time')} className="full" hint={t('Overrides the category\'s tax tag for this one transaction.')}>
          <select className="input" value={f.tax_tag} onChange={set('tax_tag')}>
            <option value="">{t('Use the category\'s tag')}</option>
            <option value="none">{t('Not deductible')}</option>
            {Object.entries(tags).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <button hidden />
      </form>
      <div className="dialog-foot" style={{ margin: '18px -22px -20px' }}>
        <button className="btn" onClick={onClose}>{t('Cancel')}</button>
        <button className="btn primary" onClick={save} disabled={busy || !f.amount || !f.description}>{t('Save')}</button>
      </div>
    </>
  )
}

function SplitEditor({ tx, categories, onSaved }) {
  const toast = useToast()
  const detail = useData(() => api.get(`/transactions/${tx.id}/detail`), [tx.id])
  const [lines, setLines] = useState(null)
  if (!detail.data) return null
  const sign = tx.amount < 0 ? -1 : 1
  const rows = lines ?? (detail.data.splits.length
    ? detail.data.splits.map((s) => ({ category_id: s.category_id, amount: Math.abs(s.amount), note: s.note }))
    : [{ category_id: tx.category_id, amount: Math.abs(tx.amount), note: '' }, { category_id: null, amount: 0, note: '' }])
  const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0)
  const left = Math.round((Math.abs(tx.amount) - total) * 100) / 100
  const update = (i, patch) => setLines(rows.map((r, n) => (n === i ? { ...r, ...patch } : r)))
  const save = async (clear) => {
    try {
      await api.put(`/transactions/${tx.id}/splits`, { lines: clear ? [] : rows.map((r) => ({ ...r, amount: sign * Number(r.amount) })) })
      toast(clear ? t('Split removed') : t('Split saved'))
      setLines(null); detail.reload(); onSaved()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="small muted">{t('Divide this transaction across categories, like groceries and household items on one receipt.')} <Money value={Math.abs(tx.amount)} currency={tx.currency} className="strong" /></p>
      {rows.map((r, i) => (
        <div key={i} className="row wrap" style={{ alignItems: 'flex-end' }}>
          <Field label={i === 0 ? t('Category') : ''} className="grow"><CategorySelect categories={categories} value={r.category_id} onChange={(v) => update(i, { category_id: v })} /></Field>
          <Field label={i === 0 ? t('Amount') : ''}><input className="input" style={{ width: 120 }} type="number" min="0" step="0.01" value={r.amount} onChange={(e) => update(i, { amount: e.target.value })} /></Field>
          <Field label={i === 0 ? t('Note') : ''}><input className="input" style={{ width: 160 }} value={r.note} onChange={(e) => update(i, { note: e.target.value })} /></Field>
          <button className="icon-btn" aria-label={t('Remove line')} disabled={rows.length <= 2} onClick={() => setLines(rows.filter((_, n) => n !== i))}><Trash2 /></button>
        </div>
      ))}
      <div className="row wrap">
        <button className="btn sm" onClick={() => setLines([...rows, { category_id: null, amount: Math.max(left, 0), note: '' }])}><Plus />{t('Add a line')}</button>
        <span className="spacer" />
        <span className={`small strong ${left === 0 ? 'income' : 'expense'}`}>{left === 0 ? t('Adds up') : t('{amount} left to assign', { amount: left.toFixed(2) })}</span>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {detail.data.splits.length > 0 && <button className="btn danger" onClick={() => save(true)}>{t('Remove split')}</button>}
        <button className="btn primary" disabled={left !== 0} onClick={() => save(false)}>{t('Save split')}</button>
      </div>
    </div>
  )
}

function ShareEditor({ tx, onSaved }) {
  const toast = useToast()
  const detail = useData(() => api.get(`/transactions/${tx.id}/detail`), [tx.id])
  const people = useData(() => api.get('/people'), [])
  const [rows, setRows] = useState(null)
  const [newName, setNewName] = useState('')
  if (!detail.data || !people.data) return null
  const list = people.data.people.filter((p) => !p.is_archived)
  const current = rows ?? Object.fromEntries(detail.data.shares.map((s) => [s.person_id, s.amount]))
  const total = Math.abs(tx.amount)
  const sharedSum = Object.values(current).reduce((s, v) => s + Number(v || 0), 0)
  const evenly = () => {
    const ids = list.map((p) => p.id)
    const each = Math.round((total / (ids.length + 1)) * 100) / 100
    setRows(Object.fromEntries(ids.map((id) => [id, each])))
  }
  const save = async () => {
    try {
      await api.put(`/transactions/${tx.id}/shares`, { shares: Object.entries(current).filter(([, v]) => Number(v) > 0).map(([id, v]) => ({ person_id: Number(id), amount: Number(v) })) })
      toast(t('Shares saved'))
      setRows(null); detail.reload(); onSaved()
    } catch (e) { toast(e.message, 'error') }
  }
  const addPerson = async () => { await api.post('/people', { name: newName }); setNewName(''); people.reload() }
  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="small muted">{t('Who owes you part of this payment? Their part is left out of your spending and added to what they owe you.')}</p>
      {list.map((p) => (
        <div key={p.id} className="row">
          <span className="avatar">{p.name[0].toUpperCase()}</span>
          <span className="grow strong" style={{ flex: 1 }}>{p.name}</span>
          <input className="input" style={{ width: 130 }} type="number" min="0" step="0.01" value={current[p.id] ?? ''} placeholder="0.00"
            onChange={(e) => setRows({ ...current, [p.id]: e.target.value })} aria-label={t('{name} owes', { name: p.name })} />
        </div>
      ))}
      <div className="row">
        <input className="input" placeholder={t('Add someone new…')} value={newName} onChange={(e) => setNewName(e.target.value)} />
        <button className="btn" onClick={addPerson} disabled={!newName.trim()}><Plus />{t('Add')}</button>
      </div>
      <div className="row wrap">
        {list.length > 0 && <button className="btn sm" onClick={evenly}>{t('Split evenly with everyone')}</button>}
        <span className="spacer" />
        <span className="small">{t('Your part')}: <Money value={total - sharedSum} currency={tx.currency} className="strong" /></span>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" onClick={save} disabled={sharedSum > total + 0.001}>{t('Save shares')}</button></div>
    </div>
  )
}

function Receipts({ tx, onSaved }) {
  const toast = useToast()
  const files = useData(() => api.get(`/transactions/${tx.id}/attachments`), [tx.id])
  const input = useRef(null)
  const [busy, setBusy] = useState(false)
  const upload = async (file) => {
    const fd = new FormData()
    fd.append('file', file)
    setBusy(true)
    try { await api.upload(`/transactions/${tx.id}/attachments`, fd); files.reload(); onSaved() } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="dropzone" role="button" tabIndex={0} onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]) }}>
        <Upload size={22} style={{ marginBottom: 6 }} />
        <div><strong>{busy ? t('Uploading…') : t('Add a receipt photo or PDF')}</strong></div>
        <div className="small">{t('Up to 10 MB. Stored on this server only.')}</div>
        <input ref={input} type="file" hidden accept="image/jpeg,image/png,image/webp,image/heic,application/pdf" capture="environment" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
      </div>
      {(files.data ?? []).map((a) => (
        <div key={a.id} className="card" style={{ boxShadow: 'none' }}>
          <div className="list-row" style={{ alignItems: 'flex-start' }}>
            {a.content_type.startsWith('image/') && a.content_type !== 'image/heic'
              ? <a href={a.url} target="_blank" rel="noreferrer"><img src={a.url} alt={a.filename} style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 8, border: '1px solid var(--rule)' }} /></a>
              : <span className="tile"><FileText /></span>}
            <div className="grow">
              <a href={a.url} target="_blank" rel="noreferrer" className="title">{a.filename}</a>
              <div className="meta">{(a.size / 1024).toFixed(0)} KB · {a.ocr_status === 'done' ? t('text read') : a.ocr_status === 'pending' ? t('reading text…') : a.ocr_status === 'failed' ? t('couldn\'t read text') : t('text reading off')}</div>
              {a.total_guess != null && Math.abs(a.total_guess - Math.abs(tx.amount)) > 0.009 && (
                <div className="small" style={{ color: 'var(--tray-ink)', marginTop: 4 }}>{t('The receipt total looks like {total}, but the transaction is {amount}.', { total: a.total_guess.toFixed(2), amount: Math.abs(tx.amount).toFixed(2) })}</div>
              )}
              {a.ocr_text && <details style={{ marginTop: 6 }}><summary className="small" style={{ cursor: 'pointer' }}>{t('Show text')}</summary><pre className="small" style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', background: 'var(--sheet-2)', padding: 10, borderRadius: 8 }}>{a.ocr_text}</pre></details>}
              {a.ocr_error && <div className="small muted">{a.ocr_error}</div>}
            </div>
            <div className="row" style={{ gap: 0 }}>
              {a.ocr_status !== 'none' && <button className="icon-btn" title={t('Read text again')} aria-label={t('Read text again')} onClick={async () => { try { await api.post(`/attachments/${a.id}/ocr`); files.reload() } catch (e) { toast(e.message, 'error') } }}><RefreshCw /></button>}
              <button className="icon-btn" aria-label={t('Delete')} onClick={async () => { await api.del(`/attachments/${a.id}`); files.reload(); onSaved() }}><Trash2 /></button>
            </div>
          </div>
        </div>
      ))}
      {files.data?.length === 0 && <p className="small muted"><Paperclip size={13} style={{ verticalAlign: -2 }} /> {t('No receipts yet. Receipt text is searchable from the transaction list once read.')}</p>}
    </div>
  )
}
