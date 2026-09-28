import { useState } from 'react'
import { Car, Gem, Home, Landmark, LineChart, Pencil, PiggyBank, Plus, Trash2, Wallet, Package, HandCoins } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { CURRENCIES, date, todayISO } from '../lib/format'
import { t } from '../i18n'

// Labels stay English here (AssetDialog matches on them); they are translated at render.
const KINDS = {
  real_estate: ['Home or property', Home, '#6366F1'], vehicle: ['Vehicle', Car, '#0EA5E9'], investment: ['Investments', LineChart, '#8B5CF6'],
  retirement: ['RRSP / TFSA / pension', PiggyBank, '#10B981'], cash: ['Cash', Wallet, '#F59E0B'], valuables: ['Valuables', Gem, '#EC4899'],
  other: ['Other asset', Package, '#64748B'], mortgage: ['Mortgage', Landmark, '#F43F5E'], loan: ['Loan / line of credit', HandCoins, '#F97316'],
  other_debt: ['Other debt', HandCoins, '#E11D48'],
}

export default function Assets() {
  const { version, bump } = useApp()
  const assets = useData(() => api.get('/assets'), [version])
  const [editing, setEditing] = useState(null)
  const [valuing, setValuing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!assets.data) return <Loading />
  const { items, base_currency, warnings } = assets.data
  const sum = (liab) => items.filter((a) => a.is_liability === liab).reduce((s, a) => s + (a.value_converted ?? 0), 0)

  const section = (liab, title) => {
    const list = items.filter((a) => a.is_liability === liab)
    return (
      <section className="card">
        <div className="card-head"><h2>{title}</h2><strong className={liab ? 'expense' : 'income'}><Money value={liab ? -sum(true) : sum(false)} currency={base_currency} /></strong></div>
        {!list.length ? <div className="list-row muted small">{liab ? t('No mortgages or loans added.') : t('No assets added.')}</div> : (
          <div className="list">
            {list.map((a) => {
              const [label, Icon, color] = KINDS[a.kind] ?? KINDS.other
              const prev = a.history.length > 1 ? a.history[a.history.length - 2].value : null
              return (
                <div className="list-row" key={a.id}>
                  <span className="tile" style={{ '--tile': color }}><Icon /></span>
                  <div className="grow">
                    <div className="title">{a.name}</div>
                    <div className="meta">{t(label)}{a.as_of ? ` · ${t('valued {date}', { date: date(a.as_of) })}` : ''}{a.notes ? ` · ${a.notes}` : ''}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="strong"><Money value={a.value} currency={a.currency} /></div>
                    {prev != null && <div className="meta"><Money value={a.value - prev} currency={a.currency} sign colored={!a.is_liability} /> {t('since last value')}</div>}
                  </div>
                  <div className="actions">
                    <button className="btn sm" onClick={() => setValuing(a)}>{t('Update value')}</button>
                    <button className="icon-btn" onClick={() => setEditing(a)} aria-label={t('Edit')}><Pencil /></button>
                    <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete {name}?', { name: a.name }), body: t('Its value history is removed too.'), onConfirm: async () => { await api.del(`/assets/${a.id}`); bump() } })}><Trash2 /></button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    )
  }

  return (
    <>
      <PageHead title={t('Assets')} sub={t('Things you own and debts you owe outside your bank accounts. They count toward net worth.')}>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add asset or debt')}</button>
      </PageHead>
      <div className="stack">
        <Warnings items={warnings} />
        {items.length === 0 ? (
          <div className="card"><Empty icon={Home} title={t('Track what you own')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add your first asset')}</button>}>
            {t('Add your home, car, RRSP or TFSA, and your mortgage, then update the values every so often.')}
          </Empty></div>
        ) : <>{section(false, t('Assets'))}{section(true, t('Liabilities'))}</>}
      </div>
      {editing && <AssetDialog asset={editing} onClose={() => setEditing(null)} onSaved={bump} base={base_currency} />}
      {valuing && <ValueDialog asset={valuing} onClose={() => setValuing(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function AssetDialog({ asset, onClose, onSaved, base }) {
  const toast = useToast()
  const [f, setF] = useState({ name: asset.name ?? '', kind: asset.kind ?? 'real_estate', currency: asset.currency ?? base, notes: asset.notes ?? '', value: '', as_of: todayISO() })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    try {
      const body = { ...f, value: f.value === '' ? null : Number(f.value) }
      if (asset.id) await api.patch(`/assets/${asset.id}`, body)
      else await api.post('/assets', body)
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={asset.id ? t('Edit') : t('Add asset or debt')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={!f.name} onClick={save}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Name')} className="full"><input className="input" value={f.name} onChange={set('name')} placeholder={t('e.g. House, Honda CR-V, Mortgage')} /></Field>
        <Field label={t('Kind')}><select className="input" value={f.kind} onChange={set('kind')}>
          <optgroup label={t('Assets')}>{Object.entries(KINDS).slice(0, 7).map(([k, [l]]) => <option key={k} value={k}>{t(l)}</option>)}</optgroup>
          <optgroup label={t('Debts')}>{Object.entries(KINDS).slice(7).map(([k, [l]]) => <option key={k} value={k}>{t(l)}</option>)}</optgroup>
        </select></Field>
        <Field label={t('Currency')}><select className="input" value={f.currency} onChange={set('currency')}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
        {!asset.id && <>
          <Field label={KINDS[f.kind]?.[0].match(/mortgage|loan|debt/i) ? t('Amount owed') : t('Current value')}><input className="input" type="number" step="0.01" min="0" value={f.value} onChange={set('value')} /></Field>
          <Field label={t('As of')}><input className="input" type="date" value={f.as_of} onChange={set('as_of')} /></Field>
        </>}
        <Field label={t('Notes')} className="full"><input className="input" value={f.notes} onChange={set('notes')} /></Field>
      </div>
    </Dialog>
  )
}

function ValueDialog({ asset, onClose, onSaved }) {
  const [value, setValue] = useState(asset.value ?? '')
  const [on, setOn] = useState(todayISO())
  const save = async () => { await api.post(`/assets/${asset.id}/values`, { date: on, value: Number(value) }); onSaved(); onClose() }
  return (
    <Dialog title={t('Update {name}', { name: asset.name })} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save}>{t('Save value')}</button></>}>
      <div className="form-grid">
        <Field label={asset.is_liability ? t('Amount owed') : t('Value')}><input className="input" type="number" step="0.01" min="0" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
        <Field label={t('As of')}><input className="input" type="date" value={on} onChange={(e) => setOn(e.target.value)} /></Field>
      </div>
      {asset.history.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="small strong" style={{ marginBottom: 6 }}>{t('History')}</div>
          <div className="list card" style={{ boxShadow: 'none', maxHeight: 200, overflowY: 'auto' }}>
            {[...asset.history].reverse().map((h) => <div key={h.id} className="list-row" style={{ padding: '7px 14px' }}><span className="grow small">{date(h.date)}</span><Money value={h.value} currency={asset.currency} className="small" /></div>)}
          </div>
        </div>
      )}
    </Dialog>
  )
}
