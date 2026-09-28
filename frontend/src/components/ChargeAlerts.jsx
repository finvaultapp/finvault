// Recurring page: price changes on recurring charges and new charges that look like subscriptions.
import { useState } from 'react'
import { BellRing, TrendingUp, X } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { date, money } from '../lib/format'
import { Money, useData, useToast } from './ui'

export default function ChargeAlerts({ onAdd }) {
  const { version } = useApp()
  const toast = useToast()
  const alerts = useData(() => api.get('/alerts/charges?refresh=true'), [version])
  const [gone, setGone] = useState(new Set())
  const items = (alerts.data ?? []).filter((a) => !gone.has(a.id))
  if (!items.length) return null

  const dismiss = async (a) => {
    setGone((s) => new Set(s).add(a.id))
    try { await api.post(`/alerts/charges/${a.id}/dismiss`) } catch (e) {
      toast(e.message, 'error')
      setGone((s) => { const n = new Set(s); n.delete(a.id); return n })
    }
  }

  return (
    <section className="card charge-alerts" aria-label={t('Charge alerts')}>
      <div className="card-head"><h2 className="row" style={{ gap: 8 }}><BellRing size={16} />{t('Worth a look')}</h2><span className="small muted">{t('From your recent statements')}</span></div>
      <div className="list">
        {items.map((a) => (
          <div className="list-row" key={a.id}>
            <span className={`alert-mark ${a.kind === 'price_change' ? 'up' : 'new'}`} aria-hidden="true">{a.kind === 'price_change' ? <TrendingUp /> : <BellRing />}</span>
            <div className="grow">
              <div className="row" style={{ gap: 8 }}>
                <span className="title">{a.name}</span>
                {a.kind === 'price_change'
                  ? <span className={`pill ${a.change > 0 ? 'red' : 'green'}`}>{a.change > 0 ? t('Price went up') : t('Price went down')}</span>
                  : <span className="pill amber">{t('New subscription?')}</span>}
              </div>
              <div className="meta">
                {a.kind === 'price_change'
                  ? t('{amount} on {date}, usually {usual}', { amount: money(Math.abs(a.amount), a.currency), date: date(a.last_date, { month: 'short', day: 'numeric' }), usual: money(Math.abs(a.usual_amount), a.currency) })
                  : t('Charged {n} times about a month apart, most recently {date}', { n: a.hits, date: date(a.last_date, { month: 'short', day: 'numeric' }) })}
                {a.account_name ? ` · ${a.account_name}` : ''}
              </div>
            </div>
            {a.kind === 'price_change'
              ? <Money value={a.change} currency={a.currency} sign className={`strong ${a.change > 0 ? 'expense' : 'income'}`} />
              : <Money value={a.amount} currency={a.currency} sign colored className="strong" />}
            <div className="actions" style={{ opacity: 1 }}>
              {a.kind === 'new_subscription' && onAdd && (
                <button className="btn sm" onClick={() => onAdd({ name: a.name, amount: a.amount, account_id: a.account_id, frequency: 'monthly', suggested: true })}>{t('Track it')}</button>
              )}
              <button className="icon-btn" onClick={() => dismiss(a)} aria-label={t('Dismiss')} title={t('Dismiss')}><X /></button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
