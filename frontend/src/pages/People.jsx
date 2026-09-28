import { useState } from 'react'
import { HandCoins, Plus, Trash2, Users } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, useData, useToast } from '../components/ui'
import { date, todayISO } from '../lib/format'

export default function People() {
  const { version, bump } = useApp()
  const people = useData(() => api.get('/people'), [version])
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(false)
  const [settling, setSettling] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const activity = useData(() => (open ? api.get(`/people/${open}/activity`) : Promise.resolve(null)), [open, version])
  if (!people.data) return <Loading />
  const cur = people.data.currency
  const list = people.data.people.filter((p) => !p.is_archived)

  return (
    <>
      <PageHead title={t('Shared costs')} sub={t('Split a bill with someone and FinVault keeps count of who owes whom. Only your share counts as your spending.')}>
        <button className="btn primary" onClick={() => setAdding(true)}><Plus />{t('Add a person')}</button>
      </PageHead>
      <div className="grid-2">
        <section className="card" style={{ alignSelf: 'start' }}>
          <div className="card-head"><h2>{t('People')}</h2></div>
          {list.length === 0 ? (
            <Empty icon={Users} title={t('Nobody yet')} action={<button className="btn primary" onClick={() => setAdding(true)}><Plus />{t('Add a person')}</button>}>
              {t('Add your partner, a roommate or a friend. Then open any payment and choose "Share" to split it.')}
            </Empty>
          ) : (
            <div className="list">
              {list.map((p) => (
                <div key={p.id} className={`list-row ${open === p.id ? '' : ''}`} style={{ cursor: 'pointer', background: open === p.id ? 'var(--sheet-2)' : undefined }} onClick={() => setOpen(p.id)}>
                  <span className="avatar">{p.name[0].toUpperCase()}</span>
                  <div className="grow">
                    <div className="title">{p.name}</div>
                    <div className="meta">{p.status === 'owes you' ? t('owes you') : p.status === 'you owe' ? t('you owe') : t('all settled')}</div>
                  </div>
                  <Money value={Math.abs(p.balance)} currency={cur} className={`strong ${p.balance > 0 ? 'income' : p.balance < 0 ? 'expense' : 'muted'}`} />
                  <div className="actions" onClick={(e) => e.stopPropagation()}>
                    {p.balance !== 0 && <button className="btn sm" onClick={() => setSettling(p)}><HandCoins />{t('Settle up')}</button>}
                    <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Remove {name}?', { name: p.name }), body: t('Their shares and settlements are removed too. Your transactions stay.'), onConfirm: async () => { await api.del(`/people/${p.id}`); if (open === p.id) setOpen(null); bump() } })}><Trash2 /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="card" style={{ alignSelf: 'start' }}>
          <div className="card-head"><h2>{activity.data ? t('With {name}', { name: activity.data.person.name }) : t('Activity')}</h2></div>
          {!open ? <div className="list-row muted small">{t('Pick a person to see what you\'ve shared and paid back.')}</div> : !activity.data ? <Loading rows={3} /> : activity.data.items.length === 0 ? (
            <div className="list-row muted small">{t('Nothing shared yet.')}</div>
          ) : (
            <div className="list">
              {activity.data.items.map((i) => (
                <div className="list-row" key={`${i.kind}${i.id}`}>
                  <div className="grow">
                    <div className="title">{i.description}</div>
                    <div className="meta">{date(i.date)} · {i.kind === 'share' ? t('their share') : t('payment')}</div>
                  </div>
                  <Money value={i.amount} currency={cur} sign colored />
                  {i.kind === 'settlement' && <button className="icon-btn" aria-label={t('Delete')} onClick={async () => { await api.del(`/settlements/${i.id}`); bump() }}><Trash2 /></button>}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
      {adding && <PersonDialog onClose={() => setAdding(false)} onSaved={bump} />}
      {settling && <SettleDialog person={settling} currency={cur} onClose={() => setSettling(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function PersonDialog({ onClose, onSaved }) {
  const [name, setName] = useState('')
  const save = async () => { await api.post('/people', { name }); onSaved(); onClose() }
  return (
    <Dialog title={t('Add a person')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!name.trim()}>{t('Add')}</button></>}>
      <Field label={t('Name')}><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t('e.g. Jordan')} /></Field>
    </Dialog>
  )
}

function SettleDialog({ person, currency, onClose, onSaved }) {
  const toast = useToast()
  const theyOwe = person.balance > 0
  const [amount, setAmount] = useState(Math.abs(person.balance))
  const [on, setOn] = useState(todayISO())
  const [txId, setTxId] = useState('')
  const recent = useData(() => api.get(`/transactions${qs({ kind: theyOwe ? 'income' : 'expense', page_size: 20 })}`), [])
  const save = async () => {
    try {
      await api.post(`/people/${person.id}/settle`, { amount: (theyOwe ? 1 : -1) * Number(amount), date: on, transaction_id: txId ? Number(txId) : null })
      toast(t('Recorded'))
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={theyOwe ? t('{name} paid you back', { name: person.name }) : t('You paid {name}', { name: person.name })} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!amount}>{t('Record payment')}</button></>}>
      <div className="form-grid">
        <Field label={t('Amount ({currency})', { currency })}><input className="input" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label={t('Date')}><input className="input" type="date" value={on} onChange={(e) => setOn(e.target.value)} /></Field>
        <Field label={t('Matching bank line (optional)')} className="full" hint={t('Linking it marks that line as a reimbursement, so it doesn\'t count as income or spending.')}>
          <select className="input" value={txId} onChange={(e) => setTxId(e.target.value)}>
            <option value="">{t('Don\'t link')}</option>
            {(recent.data?.items ?? []).map((tx) => <option key={tx.id} value={tx.id}>{date(tx.date)} · {tx.description} · {tx.amount.toFixed(2)}</option>)}
          </select>
        </Field>
      </div>
    </Dialog>
  )
}
