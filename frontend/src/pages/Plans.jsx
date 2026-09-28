import { useState } from 'react'
import { AlertTriangle, ChevronDown, Info, Landmark, Plus, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, Progress, useData, useToast } from '../components/ui'
import { date, money, todayISO } from '../lib/format'

const KIND_HELP = {
  tfsa: () => t('Your TFSA room for the year is shown in CRA My Account under "RRSP and TFSA". Withdrawals are added back to your room on January 1 of the next year.'),
  rrsp: () => t('Use the RRSP deduction limit from your latest Notice of Assessment or CRA My Account. The rules allow a $2,000 cumulative over-contribution before a penalty applies.'),
  fhsa: () => t('Use your FHSA participation room from CRA My Account. The annual and lifetime limits set by CRA apply; unused room can carry forward within those limits.'),
}

function warningText(w) {
  const amount = money(w.amount, 'CAD')
  switch (w.code) {
    case 'rrsp_over_buffer': return t('Over your deduction limit by more than the $2,000 buffer ({amount} past it). A 1% monthly tax can apply to the excess.', { amount })
    case 'rrsp_in_buffer': return t('{amount} over your deduction limit, but still inside the $2,000 over-contribution buffer.', { amount })
    case 'over_room': return t('Contributions are {amount} over the room you entered. Over-contributions can be taxed at 1% per month until removed.', { amount })
    case 'tfsa_withdrawn': return t("{amount} withdrawn this year comes back as room on January 1, {year}, not this year. Re-contributing it now uses this year's room.", { amount, year: w.year })
    default: return w.code
  }
}

export default function Plans() {
  const { version, bump } = useApp()
  const plans = useData(() => api.get('/plans'), [version])
  const accounts = useData(() => api.get('/accounts'), [version])
  const [editing, setEditing] = useState(null)
  const [adding, setAdding] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!plans.data) return <Loading />
  const years = [...new Set(plans.data.map((p) => p.year))].sort((a, b) => b - a)
  const accts = accounts.data?.items ?? []

  return (
    <>
      <PageHead title={t('Registered accounts')} sub={t('Track TFSA, RRSP and FHSA contributions against the room CRA gives you. Copy the room from CRA My Account; FinVault does the counting.')}>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add room for a year')}</button>
      </PageHead>
      <div className="banner info" style={{ marginBottom: 20 }}>
        <Info />
        <div className="banner-body">{t('These are reminders to help you stay inside your limits, not tax advice. CRA\'s numbers always win, so check My Account before a big contribution.')}</div>
      </div>
      {plans.data.length === 0 ? (
        <div className="card"><Empty icon={Landmark} title={t('No registered accounts yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add room for a year')}</button>}>
          {t('Add this year\'s TFSA, RRSP or FHSA room. Link the matching account and deposits are counted automatically.')}
        </Empty></div>
      ) : years.map((y) => (
        <section key={y} style={{ marginBottom: 24 }}>
          <h2 style={{ marginBottom: 12 }}>{y}</h2>
          <div className="grid-3">
            {plans.data.filter((p) => p.year === y).map((p) => (
              <div className="card" key={p.id}>
                <div className="card-head">
                  <div><h2>{t(p.label)}</h2><div className="sub">{p.account_id ? t('Linked to {name}', { name: accts.find((a) => a.id === p.account_id)?.name ?? '…' }) : t('Entries added by hand')}</div></div>
                  <div className="row" style={{ gap: 0 }}>
                    <button className="btn sm ghost" onClick={() => setEditing(p)}>{t('Edit')}</button>
                    <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete {kind} {year}?', { kind: t(p.label), year: p.year }), body: t('Only FinVault\'s record is removed.'), onConfirm: async () => { await api.del(`/plans/${p.id}`); bump() } })}><Trash2 /></button>
                  </div>
                </div>
                <div className="card-body stack" style={{ gap: 12 }}>
                  <div className="row" style={{ alignItems: 'baseline' }}>
                    <div style={{ fontSize: 24, fontWeight: 700 }} className={p.remaining < 0 ? 'expense' : ''}><Money value={p.remaining} currency="CAD" /></div>
                    <span className="muted small">{p.remaining < 0 ? t('over your room') : t('room left')}</span>
                  </div>
                  <Progress thick value={p.percent} color={p.remaining < 0 ? 'var(--red)' : p.percent >= 90 ? 'var(--ink-2)' : 'var(--green)'} />
                  <div className="row small muted" style={{ justifyContent: 'space-between' }}>
                    <span>{t('Room')} <Money value={p.room} currency="CAD" /></span>
                    <span>{t('In')} <Money value={p.contributed} currency="CAD" /></span>
                    {p.withdrawn > 0 && <span>{t('Out')} <Money value={p.withdrawn} currency="CAD" /></span>}
                  </div>
                  {p.warnings.map((w) => (
                    <div key={w.code} className={`banner ${w.level === 'info' ? 'info' : 'warn'}`} style={w.level === 'danger' ? { borderColor: 'var(--red)', background: 'var(--red-bg)', color: 'var(--red)' } : null}>
                      <AlertTriangle /><div className="banner-body small">{warningText(w)}</div>
                    </div>
                  ))}
                  <details className="entries">
                    <summary className="small strong">{t(p.entries.length === 1 ? '{n} entry' : '{n} entries', { n: p.entries.length })}<ChevronDown aria-hidden="true" /></summary>
                    <div className="list" style={{ marginTop: 8 }}>
                      {p.entries.map((e) => (
                        <div key={e.id} className="row small" style={{ padding: '6px 0' }}>
                          <span className="muted" style={{ width: 86 }}>{date(e.date)}</span>
                          <span className="grow" style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.note || (e.amount > 0 ? t('Contribution') : t('Withdrawal'))}</span>
                          <Money value={e.amount} currency="CAD" sign colored />
                          {e.source === 'manual' && <button className="icon-btn" aria-label={t('Delete')} onClick={async () => { await api.del(`/plans/${p.id}/entries/${e.id}`); bump() }}><Trash2 size={14} /></button>}
                        </div>
                      ))}
                    </div>
                  </details>
                  <button className="btn sm" onClick={() => setAdding(p)}><Plus />{t('Add contribution or withdrawal')}</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {editing && <PlanDialog plan={editing} accounts={accts} onClose={() => setEditing(null)} onSaved={bump} />}
      {adding && <EntryDialog plan={adding} onClose={() => setAdding(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function PlanDialog({ plan, accounts, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ kind: plan.kind ?? 'tfsa', year: plan.year ?? new Date().getFullYear(), room: plan.room ?? '', account_id: plan.account_id ?? '', notes: plan.notes ?? '' })
  const save = async () => {
    const body = { ...f, year: Number(f.year), room: Number(f.room), account_id: f.account_id ? Number(f.account_id) : null }
    try { plan.id ? await api.patch(`/plans/${plan.id}`, body) : await api.post('/plans', body); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={plan.id ? t('Edit room') : t('Add room for a year')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={f.room === ''}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Plan')}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="tfsa">{t('TFSA')}</option><option value="rrsp">{t('RRSP')}</option><option value="fhsa">{t('FHSA')}</option></select></Field>
        <Field label={t('Tax year')}><input className="input" type="number" value={f.year} onChange={(e) => setF({ ...f, year: e.target.value })} /></Field>
        <Field label={t('Room from CRA')} className="full" hint={KIND_HELP[f.kind]()}><input className="input" type="number" min="0" step="0.01" value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })} /></Field>
        <Field label={t('Linked account')} className="full" hint={t('Deposits into this account count as contributions and withdrawals are subtracted. Lines categorized as income (interest, dividends) are ignored.')}>
          <select className="input" value={f.account_id} onChange={(e) => setF({ ...f, account_id: e.target.value })}><option value="">{t('None, I\'ll add entries by hand')}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        </Field>
        <Field label={t('Notes')} className="full"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
    </Dialog>
  )
}

function EntryDialog({ plan, onClose, onSaved }) {
  const toast = useToast()
  const [kind, setKind] = useState('in')
  const [f, setF] = useState({ date: todayISO().slice(0, 4) === String(plan.year) ? todayISO() : `${plan.year}-01-01`, amount: '', note: '' })
  const save = async () => {
    try { await api.post(`/plans/${plan.id}/entries`, { ...f, amount: (kind === 'in' ? 1 : -1) * Number(f.amount) }); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={`${t(plan.label)} ${plan.year}`} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!f.amount}>{t('Add')}</button></>}>
      <div className="form-grid">
        <div className="full segmented" style={{ width: 'fit-content' }}>
          <button className={kind === 'in' ? 'on' : ''} onClick={() => setKind('in')}>{t('Contribution')}</button>
          <button className={kind === 'out' ? 'on' : ''} onClick={() => setKind('out')}>{t('Withdrawal')}</button>
        </div>
        <Field label={t('Amount')}><input className="input" type="number" min="0" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label={t('Date')}><input className="input" type="date" min={`${plan.year}-01-01`} max={`${plan.year}-12-31`} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field label={t('Note')} className="full"><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder={t('e.g. at another bank')} /></Field>
      </div>
    </Dialog>
  )
}
