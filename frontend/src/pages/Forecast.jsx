import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, CalendarClock, Info, TrendingDown } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Empty, ErrorNote, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { date, money } from '../lib/format'
import { warningSentence } from '../lib/forecast'

const RANGES = [30, 60, 90]

export default function Forecast() {
  const { version } = useApp()
  const toast = useToast()
  const [range, setRange] = useState(90)
  const [scope, setScope] = useState('total')
  const [cushion, setCushion] = useState('')
  const f = useData(() => api.get(`/forecast${qs({ days: 90 })}`), [version])
  useEffect(() => { if (f.data) setCushion(String(f.data.cushion)) }, [f.data])

  const view = useMemo(() => {
    if (!f.data) return null
    const d = f.data
    const acct = scope === 'total' ? null : d.accounts.find((a) => String(a.id) === scope)
    const key = acct ? `a${acct.id}` : 'total'
    const series = d.series.slice(0, range + 1).map((s) => ({ date: s.date, value: s[key] }))
    let low = series[0]
    for (const s of series) if (s.value < low.value) low = s
    return { acct, key, series, low, currency: acct ? acct.currency : d.currency }
  }, [f.data, scope, range])

  if (f.error) return <ErrorNote error={f.error} />
  if (!f.data) return <Loading rows={6} />
  const d = f.data
  if (d.accounts.length === 0) {
    return (
      <>
        <PageHead title={t('Cash-flow forecast')} />
        <div className="card"><Empty icon={CalendarClock} title={t('Nothing to forecast yet')} action={<Link to="/accounts" className="btn sm">{t('Add an account')}</Link>}>{t('Add an account and a few recurring items to see where your balances are heading.')}</Empty></div>
      </>
    )
  }

  const saveCushion = async () => {
    try {
      await api.put('/forecast/settings', { cushion: Number(cushion) || 0 })
      toast(t('Cushion saved'))
      f.reload()
    } catch (e) { toast(e.message, 'error') }
  }

  const upcoming = d.upcoming.filter((u) => u.date <= d.series[range].date && (scope === 'total' || String(u.account_id) === scope))
  const cushionLine = view.acct ? (view.acct.type === 'checking' ? d.cushion : null) : null
  const horizons = view.acct ? view.acct.horizons : d.total.horizons
  const start = d.series[0][view.key]

  return (
    <>
      <PageHead title={t('Cash-flow forecast')} sub={t('Where your balances are heading over the next three months, from your recurring bills and paycheques plus your usual day-to-day spending.')}>
        <div className="segmented" role="tablist" aria-label={t('Range')}>
          {RANGES.map((r) => <button key={r} role="tab" aria-selected={range === r} className={range === r ? 'on' : ''} onClick={() => setRange(r)}>{t('{n} days', { n: r })}</button>)}
        </div>
        <select className="input" style={{ width: 200 }} value={scope} onChange={(e) => setScope(e.target.value)} aria-label={t('Account')}>
          <option value="total">{t('All accounts')}</option>
          {d.accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </PageHead>

      <div className="stack">
        <div className="banner info">
          <Info />
          <div className="banner-body">
            <strong>{t('This is an estimate, not a promise.')}</strong>{' '}
            {t('It assumes your recurring items arrive on schedule and that you keep spending about {amount} a day on everything else (your typical week over the last 90 days, leaving out bills, transfers and one-off splurges).', { amount: money(d.total.daily_spend, d.currency) })}
          </div>
        </div>
        <Warnings items={d.rate_warnings} />
        {d.warnings.map((w) => (
          <div className="banner warn" role="alert" key={w.account_id}>
            <AlertTriangle />
            <div className="banner-body"><strong>{t('Low balance ahead.')}</strong> {warningSentence(w)}</div>
          </div>
        ))}

        <section className="manifest fc-manifest">
          <div><div className="label">{t('Today')}</div><div className="value"><Money value={start} currency={view.currency} /></div><div className="foot">{view.acct ? view.acct.name : t('All accounts')}</div></div>
          {RANGES.map((h) => (
            <div key={h}>
              <div className="label">{t('In {n} days', { n: h })}</div>
              <div className={`value ${horizons[h] < 0 ? 'expense' : ''}`}><Money value={horizons[h]} currency={view.currency} /></div>
              <div className="foot"><Money value={horizons[h] - start} currency={view.currency} sign /></div>
            </div>
          ))}
          <div>
            <div className="label">{t('Lowest point')}</div>
            <div className={`value ${view.low.value < 0 ? 'expense' : ''}`}><Money value={view.low.value} currency={view.currency} /></div>
            <div className="foot">{date(view.low.date, { month: 'short', day: 'numeric' })}</div>
          </div>
        </section>

        <section className="card chart-card">
          <div className="card-head" style={{ alignItems: 'flex-start' }}>
            <div><h2>{t('Projected balance')}</h2><div className="sub">{t('The dot marks the lowest point.')}{cushionLine > 0 ? ` ${t('The dashed line is your cushion.')}` : ''}</div></div>
          </div>
          <div style={{ height: 300, padding: '14px 12px 4px 0' }}>
            <ResponsiveContainer>
              <AreaChart data={view.series} margin={{ left: 8, right: 16, top: 10 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={28} tickFormatter={(v) => date(v, { month: 'short', day: 'numeric' })} />
                <YAxis tickLine={false} axisLine={false} width={66} tickFormatter={(v) => money(v, view.currency, { compact: true })} />
                <Tooltip content={<ForecastTip currency={view.currency} />} cursor={{ stroke: 'var(--rule-2)' }} />
                <ReferenceLine y={0} stroke="var(--rule-2)" />
                {cushionLine > 0 && <ReferenceLine y={cushionLine} stroke="var(--ink-3)" strokeDasharray="4 4" />}
                <Area dataKey="value" stroke="var(--ink-2)" fill="var(--ink-3)" fillOpacity={0.12} strokeWidth={2.2} dot={false} isAnimationActive={false} />
                <ReferenceDot x={view.low.date} y={view.low.value} r={5} fill={view.low.value < 0 ? 'var(--red)' : 'var(--ink)'} stroke="var(--sheet)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        <div className="grid-2">
          <section className="card">
            <div className="card-head"><h2 className="row" style={{ gap: 8 }}><CalendarClock size={16} />{t('Coming up')}</h2><span className="small muted">{t('{n} items', { n: upcoming.length })}</span></div>
            {upcoming.length === 0 ? <div className="list-row muted small">{t('No recurring items in this window.')} <Link to="/recurring">{t('Add bills and paycheques')}</Link></div> : (
              <div className="list">
                {upcoming.map((u, i) => (
                  <div className="list-row fc-item" key={`${u.recurring_id}-${u.date}-${i}`}>
                    <div className="fc-date small strong">{date(u.date, { month: 'short', day: 'numeric' })}</div>
                    <div className="grow">
                      <div className="title">{u.name}</div>
                      <div className="meta">{u.account_name} · {t('then {amount}', { amount: money(u.balance_after, u.currency) })}{u.below_cushion && <> · <span className="pill red">{t('below cushion')}</span></>}</div>
                    </div>
                    <Money value={u.amount} currency={u.currency} sign colored className="strong" />
                  </div>
                ))}
              </div>
            )}
          </section>

          <div className="stack">
            <section className="card">
              <div className="card-head"><h2 className="row" style={{ gap: 8 }}><TrendingDown size={16} />{t('By account')}</h2></div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>{t('Account')}</th><th className="amount">{t('Today')}</th><th className="amount">{t('In {n} days', { n: range })}</th><th className="amount hide-sm">{t('Lowest')}</th><th className="amount hide-sm">{t('Per day')}</th></tr></thead>
                  <tbody>
                    {d.accounts.map((a) => (
                      <tr key={a.id}>
                        <td className="desc"><div>{a.name}</div>{a.warning && <small className="expense">{t('Low balance ahead')}</small>}</td>
                        <td className="amount"><Money value={a.balance} currency={a.currency} /></td>
                        <td className="amount"><Money value={a.horizons[range]} currency={a.currency} /></td>
                        <td className="amount hide-sm"><Money value={a.lowest.balance} currency={a.currency} /><div className="small muted" style={{ fontWeight: 400 }}>{date(a.lowest.date, { month: 'short', day: 'numeric' })}</div></td>
                        <td className="amount hide-sm"><Money value={-a.daily_spend} currency={a.currency} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="card">
              <div className="card-head"><div><h2>{t('Cushion')}</h2><div className="sub">{t('Warn me when a chequing account is projected to dip below this amount before a bill.')}</div></div></div>
              <div className="card-body row" style={{ alignItems: 'flex-end' }}>
                <Field label={t('Keep at least')} className="grow"><input className="input" type="number" min="0" step="50" value={cushion} onChange={(e) => setCushion(e.target.value)} /></Field>
                <button className="btn primary" onClick={saveCushion} disabled={String(d.cushion) === cushion}>{t('Save')}</button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </>
  )
}

function ForecastTip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="t">{date(label)}</div>
      <div>{t('Projected')}: <strong>{money(payload[0].value, currency)}</strong></div>
    </div>
  )
}
