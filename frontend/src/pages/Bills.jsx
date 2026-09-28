import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, BellOff, ChevronLeft, ChevronRight, Send } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Field, Loading, Money, PageHead, Switch, useData, useToast } from '../components/ui'
import { addMonths, currentLocale, monthLabel, todayISO } from '../lib/format'

export default function Bills() {
  const { version, bump } = useApp()
  const [month, setMonth] = useState(todayISO().slice(0, 7))
  const cal = useData(() => api.get(`/bills/calendar${qs({ month })}`), [month, version])
  const rec = useData(() => api.get('/recurring'), [version])
  if (!cal.data || !rec.data) return <Loading />

  const [y, m] = month.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const days = new Date(y, m, 0).getDate()
  const lead = (first.getDay() + 6) % 7 // Monday first
  const byDay = {}
  for (const i of cal.data.items) (byDay[Number(i.date.slice(8, 10))] ??= []).push(i)
  const today = todayISO()
  const weekdays = Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(currentLocale(), { weekday: 'short' }))
  const total = cal.data.items.filter((i) => i.amount < 0).reduce((s, i) => s + i.amount, 0)

  return (
    <>
      <PageHead title={t('Bills')} sub={t('Everything recurring, laid out by day, with reminders before each one is due.')}>
        <button className="icon-btn bordered" onClick={() => setMonth(addMonths(month, -1))} aria-label={t('Previous month')}><ChevronLeft /></button>
        <span className="strong" style={{ minWidth: 140, textAlign: 'center' }}>{monthLabel(month)}</span>
        <button className="icon-btn bordered" onClick={() => setMonth(addMonths(month, 1))} aria-label={t('Next month')}><ChevronRight /></button>
        <Link to="/recurring" className="btn">{t('Manage recurring')}</Link>
      </PageHead>
      <div className="stack">
        <section className="card">
          <div className="card-head"><h2>{monthLabel(month)}</h2><span className="small muted">{t('Bills this month')}: <Money value={-total} currency="CAD" className="strong expense" /></span></div>
          <div className="calendar">
            {weekdays.map((w) => <div key={w} className="cal-wd">{w}</div>)}
            {Array.from({ length: lead }, (_, i) => <div key={`l${i}`} className="cal-day empty" />)}
            {Array.from({ length: days }, (_, i) => {
              const d = i + 1
              const iso = `${month}-${String(d).padStart(2, '0')}`
              return (
                <div key={d} className={`cal-day ${iso === today ? 'today' : ''}`}>
                  <span className="cal-n">{d}</span>
                  {(byDay[d] ?? []).map((b) => (
                    <div key={b.recurring_id + b.date} className={`cal-bill ${b.amount > 0 ? 'in' : ''}`} title={`${b.name} · ${b.account_name ?? ''}`}>
                      {b.remind_days != null && <Bell size={10} />}
                      <span className="cal-name">{b.name}</span>
                      <Money value={Math.abs(b.amount)} currency={b.currency ?? 'CAD'} compact />
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </section>
        <div className="grid-2">
          <Reminders items={rec.data.items} onSaved={bump} />
          <NotifySettings />
        </div>
      </div>
    </>
  )
}

function Reminders({ items, onSaved }) {
  const toast = useToast()
  const set = async (r, value) => {
    try { await api.put(`/recurring/${r.id}/reminder`, { remind_days: value === '' ? null : Number(value) }); onSaved() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <section className="card" style={{ alignSelf: 'start' }}>
      <div className="card-head"><div><h2>{t('Reminders')}</h2><div className="sub">{t('How early to be told about each bill.')}</div></div></div>
      {items.length === 0 ? <div className="list-row muted small">{t('Nothing recurring yet.')} <Link to="/recurring">{t('Add a bill')}</Link></div> : (
        <div className="list">
          {items.filter((r) => r.is_active).map((r) => (
            <div className="list-row" key={r.id} style={{ padding: '9px 18px' }}>
              {r.remind_days != null ? <Bell size={16} style={{ color: 'var(--frame)' }} /> : <BellOff size={16} className="muted" />}
              <div className="grow"><div className="title">{r.name}</div><div className="meta"><Money value={r.amount} currency={r.currency} /></div></div>
              <select className="input sm" style={{ width: 170 }} value={r.remind_days ?? ''} onChange={(e) => set(r, e.target.value)} aria-label={t('Reminder for {name}', { name: r.name })}>
                <option value="">{t('No reminder')}</option>
                <option value="0">{t('On the day')}</option>
                <option value="1">{t('1 day before')}</option>
                {[2, 3, 5, 7, 14].map((n) => <option key={n} value={n}>{t('{n} days before', { n })}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function NotifySettings() {
  const toast = useToast()
  const s = useData(() => api.get('/notifications'), [])
  const [f, setF] = useState(null)
  if (!s.data) return <Loading rows={2} />
  const v = f ?? { ntfy_url: s.data.ntfy_url, email: s.data.email, hide_amounts: s.data.hide_amounts }
  const save = async (next) => {
    setF(next)
    try { await api.put('/notifications', next); s.reload(); setF(null) } catch (e) { toast(e.message, 'error') }
  }
  const test = async () => { try { const r = await api.post('/notifications/test'); toast(t('Sent by {channels}', { channels: r.sent.join(', ') })) } catch (e) { toast(e.message, 'error') } }
  return (
    <section className="card" id="notifications" style={{ alignSelf: 'start' }}>
      <div className="card-head"><div><h2>{t('Where reminders go')}</h2><div className="sub">{t('Nothing is sent until you set one of these up.')}</div></div></div>
      <div className="card-body stack" style={{ gap: 16 }}>
        <Field label={t('ntfy push address')} hint={t('Install the ntfy app, subscribe to a hard-to-guess topic, and paste its address. Anyone who knows a public topic can read it, so use a private or self-hosted server if you can.')}>
          <div className="row">
            <input className="input" value={v.ntfy_url} placeholder="https://ntfy.sh/finvault-a8f3k2" onChange={(e) => setF({ ...v, ntfy_url: e.target.value })} />
            <button className="btn" onClick={() => save(v)}>{t('Save')}</button>
          </div>
        </Field>
        <label className="row" style={{ gap: 12 }}>
          <Switch checked={v.email} onChange={(on) => save({ ...v, email: on })} label={t('Email')} />
          <span><span className="strong">{t('Email me at {address}', { address: s.data.address })}</span><br />
            <span className="small muted">{s.data.email_available ? t('Uses the server\'s email settings.') : t('Your admin needs to add SMTP settings to the server before email works.')}</span></span>
        </label>
        <label className="row" style={{ gap: 12 }}>
          <Switch checked={v.hide_amounts} onChange={(on) => save({ ...v, hide_amounts: on })} label={t('Hide amounts')} />
          <span><span className="strong">{t('Leave amounts out of reminders')}</span><br /><span className="small muted">{t('Useful when notifications show on a lock screen.')}</span></span>
        </label>
        <div><button className="btn" onClick={test}><Send />{t('Send a test')}</button></div>
      </div>
    </section>
  )
}
