import { useState } from 'react'
import { Pencil, Plus, PlusCircle, Target, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { CategoryTile, Confirm, Dialog, Empty, Field, Loading, Money, PageHead, Progress, useData, useToast } from '../components/ui'
import { CURRENCIES, date } from '../lib/format'
import { t } from '../i18n'

function status(g) {
  if (g.percent >= 100) return [t('Reached'), 'green']
  if (!g.target_date) return null
  const created = new Date(g.created_at ?? Date.now())
  const end = new Date(g.target_date)
  if (end < new Date()) return [t('Past target date'), 'red']
  const expected = ((Date.now() - created) / (end - created)) * 100
  return g.percent + 5 >= Math.min(expected, 100) ? [t('On track'), 'blue'] : [t('Behind'), 'amber']
}

export default function Goals() {
  const { version, bump } = useApp()
  const goals = useData(() => api.get('/goals'), [version])
  const accounts = useData(() => api.get('/accounts'), [])
  const [editing, setEditing] = useState(null)
  const [adding, setAdding] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!goals.data) return <Loading />

  return (
    <>
      <PageHead title={t('Goals')} sub={t('Savings targets. Link a goal to a savings account to track its balance automatically.')}>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add goal')}</button>
      </PageHead>
      <section className="card">
        {goals.data.length === 0 ? (
          <Empty icon={Target} title={t('No goals yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add a goal')}</button>}>
            {t('An emergency fund, a trip, a down payment. Set the amount and a date, and FinVault works out the monthly amount.')}
          </Empty>
        ) : (
          <div className="list">
            {goals.data.map((g) => {
              const s = status(g)
              return (
                <div className="list-row" key={g.id} style={{ alignItems: 'flex-start' }}>
                  <CategoryTile name={g.name.match(/trip|travel|vacation/i) ? 'travel' : g.name.match(/car/i) ? 'car' : g.name.match(/home|house/i) ? 'home' : 'saving'} color="#6366F1" />
                  <div className="grow">
                    <div className="row" style={{ gap: 8 }}>
                      <span className="title">{g.name}</span>
                      {s && <span className={`pill ${s[1]}`}>{s[0]}</span>}
                      {g.account_id && <span className="pill">{t('Linked account')}</span>}
                      {g.missing_rate && <span className="pill amber">{t('Needs exchange rate')}</span>}
                    </div>
                    <div className="row" style={{ marginTop: 9 }}>
                      <div style={{ flex: 1 }}><Progress thick value={g.percent} color={g.percent >= 100 ? 'var(--income)' : 'var(--warn-strong)'} /></div>
                      <span className="strong small num" style={{ width: 44, textAlign: 'right' }}>{Math.round(g.percent ?? 0)}%</span>
                    </div>
                    <div className="meta" style={{ marginTop: 6 }}>
                      <Money value={g.saved} currency={g.currency} /> {t('of')} <Money value={g.target_amount} currency={g.currency} />
                      {g.monthly_needed != null && <> · <Money value={g.monthly_needed} currency={g.currency} />{t('/mo')}</>}
                      {g.target_date && <> · {t('by {date}', { date: date(g.target_date) })}</>}
                    </div>
                  </div>
                  <div className="actions">
                    {!g.account_id && <button className="icon-btn" onClick={() => setAdding(g)} aria-label={t('Add money')} title={t('Add money')}><PlusCircle /></button>}
                    <button className="icon-btn" onClick={() => setEditing(g)} aria-label={t('Edit')}><Pencil /></button>
                    <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete “{name}”?', { name: g.name }), body: t('Only the goal is removed; no transactions change.'), onConfirm: async () => { await api.del(`/goals/${g.id}`); bump() } })}><Trash2 /></button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
      {editing && <GoalDialog goal={editing} accounts={accounts.data?.items ?? []} onClose={() => setEditing(null)} onSaved={bump} />}
      {adding && <ContributeDialog goal={adding} onClose={() => setAdding(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function GoalDialog({ goal, accounts, onClose, onSaved }) {
  const toast = useToast()
  const { user } = useApp()
  const [f, setF] = useState({ name: goal.name ?? '', target_amount: goal.target_amount ?? '', currency: goal.currency ?? user.base_currency,
    target_date: goal.target_date ?? '', account_id: goal.account_id ?? '', saved_amount: goal.saved_amount ?? 0 })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    const body = { ...f, target_amount: Number(f.target_amount), saved_amount: Number(f.saved_amount) || 0, target_date: f.target_date || null, account_id: f.account_id ? Number(f.account_id) : null }
    try { goal.id ? await api.patch(`/goals/${goal.id}`, body) : await api.post('/goals', body); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={goal.id ? t('Edit goal') : t('New goal')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={!f.name || !f.target_amount} onClick={save}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Goal')} className="full"><input className="input" value={f.name} onChange={set('name')} placeholder={t('e.g. Emergency fund')} /></Field>
        <Field label={t('Target amount')}><input className="input" type="number" min="1" value={f.target_amount} onChange={set('target_amount')} /></Field>
        <Field label={t('Currency')}><select className="input" value={f.currency} onChange={set('currency')}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label={t('Target date')} hint={t('Optional')}><input className="input" type="date" value={f.target_date} onChange={set('target_date')} /></Field>
        <Field label={t("Track an account's balance")} hint={t('Optional. Otherwise add money by hand.')}>
          <select className="input" value={f.account_id} onChange={set('account_id')}><option value="">{t('Track by hand')}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        {!f.account_id && <Field label={t('Saved so far')}><input className="input" type="number" min="0" value={f.saved_amount} onChange={set('saved_amount')} /></Field>}
      </div>
    </Dialog>
  )
}

function ContributeDialog({ goal, onClose, onSaved }) {
  const [amount, setAmount] = useState('')
  const save = async () => { await api.post(`/goals/${goal.id}/contribute`, { amount: Number(amount) }); onSaved(); onClose() }
  return (
    <Dialog title={t('Add to {name}', { name: goal.name })} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!amount}>{t('Add')}</button></>}>
      <Field label={t('Amount ({currency})', { currency: goal.currency })} hint={t('Use a negative number to take money out.')}><input className="input" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
    </Dialog>
  )
}
