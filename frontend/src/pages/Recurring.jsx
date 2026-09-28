import { useState } from 'react'
import { CalendarClock, FastForward, Pencil, Plus, Repeat, Sparkles, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { CategoryTile, Confirm, Dialog, Empty, Field, Loading, Money, PageHead, Switch, useData, useToast } from '../components/ui'
import { CategorySelect } from '../components/TxDialog'
import { date, relativeDays, todayISO } from '../lib/format'
import { t } from '../i18n'

const FREQ = { weekly: 'Weekly', biweekly: 'Every 2 weeks', monthly: 'Monthly', quarterly: 'Quarterly', yearly: 'Yearly' }

export default function Recurring() {
  const { version, bump } = useApp()
  const rec = useData(() => api.get('/recurring'), [version])
  const sugg = useData(() => api.get('/recurring/suggestions'), [version])
  const accounts = useData(() => api.get('/accounts'), [])
  const cats = useData(() => api.get('/categories'), [])
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!rec.data || !cats.data) return <Loading />
  const catById = Object.fromEntries(cats.data.map((c) => [c.id, c]))

  return (
    <>
      <PageHead title={t('Recurring')} sub={t('Bills, subscriptions and paycheques. Turn on auto-post to have FinVault add them on the due date.')}>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add recurring')}</button>
      </PageHead>
      <div className="grid-2" style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)' }}>
        <div className="stack">
          <section className="card">
            <div className="card-head"><h2>{t('Scheduled')}</h2>
              {Object.entries(rec.data.monthly_outflow_by_currency).map(([c, v]) => <span key={c} className="small muted">≈ <Money value={v} currency={c} className="strong" /> {t('out per month')}</span>)}
            </div>
            {rec.data.items.length === 0 ? <Empty icon={Repeat} title={t('Nothing scheduled yet')}>{t('Add rent, phone, streaming and paycheques, or accept a suggestion.')}</Empty> : (
              <div className="list">
                {rec.data.items.map((r) => {
                  const c = catById[r.category_id]
                  return (
                    <div className="list-row" key={r.id} style={{ opacity: r.is_active ? 1 : 0.5 }}>
                      <CategoryTile name={c?.name ?? r.name} color={c?.color} />
                      <div className="grow">
                        <div className="row" style={{ gap: 8 }}><span className="title">{r.name}</span>{r.auto_post && <span className="pill indigo">{t('Auto-post')}</span>}</div>
                        <div className="meta">{t(FREQ[r.frequency])} · {r.account_name} · {t('next {date}', { date: date(r.next_date) })} ({relativeDays(r.next_date)})</div>
                      </div>
                      <Money value={r.amount} currency={r.currency} sign colored className="strong" />
                      <div className="actions">
                        <button className="icon-btn" title={t('Skip next')} aria-label={t('Skip next')} onClick={async () => { await api.post(`/recurring/${r.id}/skip`); rec.reload() }}><FastForward /></button>
                        <button className="icon-btn" onClick={() => setEditing(r)} aria-label={t('Edit')}><Pencil /></button>
                        <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete “{name}”?', { name: r.name }), body: t('Transactions it already posted stay.'), onConfirm: async () => { await api.del(`/recurring/${r.id}`); bump() } })}><Trash2 /></button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
          {sugg.data?.length > 0 && (
            <section className="card">
              <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Sparkles size={16} />{t('Looks recurring')}</h2><span className="small muted">{t('Found in your history')}</span></div>
              <div className="list">
                {sugg.data.map((s) => (
                  <div className="list-row" key={s.name}>
                    <div className="grow">
                      <div className="title">{s.name}</div>
                      <div className="meta">{t(FREQ[s.frequency])} · {t(s.occurrences === 1 ? 'seen {n} time' : 'seen {n} times', { n: s.occurrences })} · {t('next around {date}', { date: date(s.next_date) })}</div>
                    </div>
                    <Money value={s.amount} currency={accounts.data?.items.find((a) => a.id === s.account_id)?.currency} sign colored />
                    <button className="btn sm" onClick={() => setEditing({ ...s, suggested: true })}>{t('Add')}</button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
        <section className="card" style={{ alignSelf: 'start' }}>
          <div className="card-head"><h2 className="row" style={{ gap: 8 }}><CalendarClock size={16} />{t('Next 45 days')}</h2></div>
          {rec.data.upcoming.length === 0 ? <div className="list-row muted small">{t('Nothing due.')}</div> : (
            <div className="list">
              {rec.data.upcoming.map((u, i) => (
                <div className="list-row" key={i} style={{ padding: '10px 22px' }}>
                  <div style={{ width: 54 }} className="small strong num">{date(u.date, { month: 'short', day: 'numeric' })}</div>
                  <div className="grow small">{u.name}</div>
                  <Money value={u.amount} currency={u.currency} sign colored className="small strong" />
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
      {editing && <RecurringDialog item={editing} accounts={accounts.data?.items ?? []} cats={cats.data} onClose={() => setEditing(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function RecurringDialog({ item, accounts, cats, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ name: item.name ?? '', kind: (item.amount ?? -1) < 0 ? 'out' : 'in', amount: item.amount != null ? Math.abs(item.amount) : '',
    account_id: item.account_id ?? accounts[0]?.id, category_id: item.category_id ?? null, frequency: item.frequency ?? 'monthly',
    next_date: item.next_date ?? todayISO(), end_date: item.end_date ?? '', auto_post: item.auto_post ?? false, is_active: item.is_active ?? true })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    const body = { ...f, amount: (f.kind === 'out' ? -1 : 1) * Number(f.amount), account_id: Number(f.account_id), end_date: f.end_date || null }
    try { item.id && !item.suggested ? await api.patch(`/recurring/${item.id}`, body) : await api.post('/recurring', body); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={item.id && !item.suggested ? t('Edit recurring') : t('Add recurring')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!f.name || !f.amount}>{t('Save')}</button></>}>
      <div className="form-grid">
        <div className="full segmented" style={{ width: 'fit-content' }}>
          <button type="button" className={f.kind === 'out' ? 'on' : ''} onClick={() => setF({ ...f, kind: 'out' })}>{t('Bill / money out')}</button>
          <button type="button" className={f.kind === 'in' ? 'on' : ''} onClick={() => setF({ ...f, kind: 'in' })}>{t('Income')}</button>
        </div>
        <Field label={t('Name')} className="full"><input className="input" value={f.name} onChange={set('name')} placeholder={t('e.g. Rent, Netflix, Payroll')} /></Field>
        <Field label={t('Amount')}><input className="input" type="number" min="0" step="0.01" value={f.amount} onChange={set('amount')} /></Field>
        <Field label={t('How often')}><select className="input" value={f.frequency} onChange={set('frequency')}>{Object.entries(FREQ).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></Field>
        <Field label={t('Next date')}><input className="input" type="date" value={f.next_date} onChange={set('next_date')} /></Field>
        <Field label={t('Ends')} hint={t('Optional')}><input className="input" type="date" value={f.end_date} onChange={set('end_date')} /></Field>
        <Field label={t('Account')}><select className="input" value={f.account_id} onChange={set('account_id')}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label={t('Category')}><CategorySelect categories={cats} value={f.category_id} onChange={(v) => setF({ ...f, category_id: v })} /></Field>
        <label className="full row" style={{ gap: 12 }}>
          <Switch checked={f.auto_post} onChange={(v) => setF({ ...f, auto_post: v })} label={t('Auto-post')} />
          <span><span className="strong">{t('Auto-post on the due date')}</span><br /><span className="small muted">{t("Leave off if these already arrive in your bank imports; otherwise they'd be counted twice.")}</span></span>
        </label>
      </div>
    </Dialog>
  )
}
