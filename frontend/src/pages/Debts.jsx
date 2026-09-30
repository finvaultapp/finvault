import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Info, Mountain, Snowflake, Wallet } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Empty, ErrorNote, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { money, monthLabel, shortMonth } from '../lib/format'

const KINDS = { card: 'Credit card', loan: 'Loan', mortgage: 'Mortgage' }

function duration(months) {
  const y = Math.floor(months / 12)
  const m = months % 12
  if (!y) return t(m === 1 ? '{m} month' : '{m} months', { m })
  if (!m) return t(y === 1 ? '{y} year' : '{y} years', { y })
  return t('{y} yr {m} mo', { y, m })
}

export default function Debts() {
  const { version } = useApp()
  const debts = useData(() => api.get('/debts'), [version])
  const [budget, setBudget] = useState(null)
  const [touched, setTouched] = useState(false)
  const [extra, setExtra] = useState(0)
  const [plan, setPlan] = useState(null)
  const [planError, setPlanError] = useState(null)
  const [tick, setTick] = useState(0)

  const configured = debts.data?.items.filter((d) => d.configured && d.balance > 0) ?? []
  const minimums = configured.reduce((s, d) => s + Math.min(d.min_payment, d.balance_converted ?? d.balance), 0)

  useEffect(() => {
    // Until the member types a budget, suggest the saved one or about 20% over the minimums.
    const saved = debts.data?.budget
    if (debts.data && !touched) setBudget(String(saved != null && saved >= minimums ? saved : Math.ceil((minimums * 1.2) / 50) * 50))
  }, [debts.data]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (budget === null || !configured.length) { setPlan(null); return undefined }
    const id = setTimeout(() => {
      api.post('/debts/plan', { budget: Number(budget) || 0, extra: Number(extra) || 0 })
        .then((p) => { setPlan(p); setPlanError(null) }, setPlanError)
    }, 250)
    return () => clearTimeout(id)
  }, [budget, extra, tick, configured.length]) // eslint-disable-line react-hooks/exhaustive-deps

  if (debts.error) return <ErrorNote error={debts.error} />
  if (!debts.data) return <Loading rows={6} />
  const cur = debts.data.currency
  const items = debts.data.items

  return (
    <>
      <PageHead title={t('Debt payoff')} sub={t('Pick a monthly amount for your debts and compare two ways to pay them down: the avalanche method and the snowball method.')} />
      {items.length === 0 ? (
        <div className="card"><Empty icon={Wallet} title={t('No debts to plan')} action={<div className="row"><Link to="/accounts" className="btn sm">{t('Add an account')}</Link><Link to="/assets" className="btn sm">{t('Add a debt')}</Link></div>}>
          {t('Credit card and loan accounts, and debts you add under Assets (like a mortgage), show up here.')}
        </Empty></div>
      ) : (
        <div className="stack">
          <Warnings items={debts.data.warnings} />
          <DebtTable items={items} onSaved={() => { debts.reload(); setTick((n) => n + 1) }} />
          <section className="card">
            <div className="card-head"><div><h2>{t('Your monthly budget')}</h2><div className="sub">{t('The total you can put toward all these debts each month. Minimum payments add up to {amount}.', { amount: money(minimums, cur) })}</div></div></div>
            <div className="card-body debt-budget">
              <Field label={t('Each month')}><input className="input" type="number" min="0" step="25" value={budget ?? ''} onChange={(e) => { setTouched(true); setBudget(e.target.value) }} /></Field>
              <label className="field grow">
                <span>{t('What if I pay {amount} more?', { amount: money(Number(extra), cur) })}</span>
                <input className="slider" type="range" min="0" max={Math.max(1000, Math.round((Number(budget) || 0) / 100) * 100)} step="25" value={extra} onChange={(e) => setExtra(Number(e.target.value))} aria-label={t('Extra each month')} />
                <small>{extra > 0 ? t('Budget with the extra: {amount} a month', { amount: money((Number(budget) || 0) + extra, cur) }) : t('Slide to see how much sooner you could be debt-free.')}</small>
              </label>
            </div>
          </section>
          {!configured.length ? (
            <div className="banner info"><Info /><div className="banner-body">{t('Enter the APR and minimum payment for at least one debt to see a plan.')}</div></div>
          ) : planError ? <ErrorNote error={planError} /> : !plan ? <Loading rows={3} /> : <Results plan={plan} items={items} extra={extra} />}
          <div className="banner ca">
            <Info />
            <div className="banner-body small">
              {t('Estimates only. Credit cards and loans are charged APR ÷ 12 each month. Canadian fixed-rate mortgages compound twice a year, so FinVault uses the effective monthly rate (1 + APR ÷ 2)^(1/6) − 1, which is a little lower. Real statements can differ with daily interest, fees, promotional rates or a changing minimum payment.')}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function DebtTable({ items, onSaved }) {
  return (
    <section className="card">
      <div className="card-head"><div><h2>{t('Your debts')}</h2><div className="sub">{t('Balances come from your accounts and assets. Add the rate and minimum from your latest statement.')}</div></div></div>
      <div className="table-wrap">
        <table className="table debt-table">
          <thead><tr><th>{t('Debt')}</th><th>{t('Type')}</th><th className="amount">{t('Balance')}</th><th>{t('APR')}</th><th>{t('Minimum payment')}</th><th /></tr></thead>
          <tbody>{items.map((d) => <DebtRow key={d.id} d={d} onSaved={onSaved} />)}</tbody>
        </table>
      </div>
    </section>
  )
}

function DebtRow({ d, onSaved }) {
  const toast = useToast()
  const init = { apr: d.apr ?? '', min_payment: d.min_payment ?? '', kind: d.kind }
  const [f, setF] = useState(init)
  const dirty = String(f.apr) !== String(init.apr) || String(f.min_payment) !== String(init.min_payment) || f.kind !== init.kind
  const save = async () => {
    try {
      await api.put(`/debts/${d.source}/${d.ref_id}`, { apr: Number(f.apr) || 0, min_payment: Number(f.min_payment) || 0, kind: f.kind })
      toast(t('Saved'))
      onSaved()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <tr>
      <td className="desc debt-name"><div>{d.name}</div>{!d.configured && <small className="tray-note">{t('Needs a rate')}</small>}</td>
      <td className="debt-field" data-label={t('Type')}><select className="input sm" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} aria-label={t('Type')}>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></td>
      <td className="amount debt-balance"><Money value={d.balance} currency={d.currency} /></td>
      <td className="debt-field" data-label={t('APR')}><div className="unit-input"><input className="input sm" type="number" min="0" max="100" step="0.01" value={f.apr} onChange={(e) => setF({ ...f, apr: e.target.value })} aria-label={t('APR for {name}', { name: d.name })} /><span>%</span></div></td>
      <td className="debt-field" data-label={t('Minimum payment')}><input className="input sm debt-min" type="number" min="0" step="1" value={f.min_payment} onChange={(e) => setF({ ...f, min_payment: e.target.value })} aria-label={t('Minimum payment for {name}', { name: d.name })} /></td>
      <td className={`debt-save ${dirty ? '' : 'idle'}`} style={{ textAlign: 'right' }}>{dirty && <button className="btn sm primary" onClick={save} disabled={f.apr === '' || f.min_payment === ''}>{t('Save')}</button>}</td>
    </tr>
  )
}

function Results({ plan, items, extra }) {
  const cur = plan.currency
  const names = Object.fromEntries(items.map((d) => [d.id, d.name]))
  const av = plan.avalanche
  const sb = plan.snowball
  const [pick, setPick] = useState('avalanche')

  const chart = useMemo(() => {
    const len = Math.max(av.schedule.length, sb.schedule.length)
    const rows = []
    for (let i = 0; i < len; i++) {
      rows.push({ month: av.schedule[i]?.month ?? sb.schedule[i]?.month, avalanche: av.schedule[i]?.total_balance ?? 0, snowball: sb.schedule[i]?.total_balance ?? 0 })
    }
    return rows
  }, [av, sb])

  if (!av.feasible || !sb.feasible) {
    const reason = av.reason ?? sb.reason
    return (
      <div className="banner warn" role="alert"><AlertTriangle /><div className="banner-body">
        {reason === 'budget_below_minimums'
          ? t('Your budget is below the minimum payments ({amount}). Raise it to at least that to see a plan.', { amount: money(plan.minimums, cur) })
          : t("At this budget the interest outpaces the payments, so the debts never get paid off. Try a bigger budget.")}
      </div></div>
    )
  }
  const cheaper = av.total_interest <= sb.total_interest ? 'avalanche' : 'snowball'
  const diff = Math.abs(av.total_interest - sb.total_interest)
  const schedule = plan[pick].schedule
  const ids = Object.keys(schedule[0]?.balances ?? {})

  return (
    <>
      <div className="grid-2 strategy-grid">
        <Strategy icon={Mountain} title={t('Avalanche method')} blurb={t('Highest APR first. Usually the least interest.')} r={av} withExtra={plan.avalanche_extra} extra={extra} names={names} currency={cur} best={cheaper === 'avalanche' && diff >= 0.01} />
        <Strategy icon={Snowflake} title={t('Snowball method')} blurb={t('Smallest balance first. Quicker early wins.')} r={sb} withExtra={plan.snowball_extra} extra={extra} names={names} currency={cur} best={cheaper === 'snowball' && diff >= 0.01} />
      </div>
      {diff >= 0.01 && <p className="small muted" style={{ margin: '-6px 4px 0' }}>{cheaper === 'avalanche' ? t('Avalanche saves {amount} in interest compared with snowball.', { amount: money(diff, cur) }) : t('Snowball saves {amount} in interest compared with avalanche.', { amount: money(diff, cur) })}</p>}
      {plan.skipped.length > 0 && <p className="small muted" style={{ margin: '0 4px' }}>{t('Not in the plan yet (no rate entered): {names}', { names: plan.skipped.map((id) => names[id]).join(', ') })}</p>}

      <section className="card chart-card">
        <div className="card-head">
          <h2>{t('What you owe over time')}</h2>
          <div className="legend"><span><i className="dot" style={{ '--dot': 'var(--frame)' }} />{t('Avalanche')}</span><span><i className="dot" style={{ '--dot': 'var(--post)' }} />{t('Snowball')}</span></div>
        </div>
        <div style={{ height: 280, padding: '14px 12px 4px 0' }}>
          <ResponsiveContainer>
            <LineChart data={chart} margin={{ left: 8, right: 16, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickLine={false} axisLine={false} minTickGap={30} tickFormatter={(m) => `${shortMonth(m)} ${m.slice(2, 4)}`} />
              <YAxis tickLine={false} axisLine={false} width={66} tickFormatter={(v) => money(v, cur, { compact: true })} />
              <Tooltip content={<DebtTip currency={cur} />} cursor={{ stroke: 'var(--rule-2)' }} />
              <Line dataKey="avalanche" name={t('Avalanche')} stroke="var(--frame)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
              <Line dataKey="snowball" name={t('Snowball')} stroke="var(--post)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{t('Month by month')}</h2>
          <div className="segmented" role="group" aria-label={t('Strategy')}>
            <button aria-pressed={pick === 'avalanche'} className={pick === 'avalanche' ? 'on' : ''} onClick={() => setPick('avalanche')}>{t('Avalanche')}</button>
            <button aria-pressed={pick === 'snowball'} className={pick === 'snowball' ? 'on' : ''} onClick={() => setPick('snowball')}>{t('Snowball')}</button>
          </div>
        </div>
        <div className="table-wrap schedule-wrap" tabIndex={0} role="region" aria-label={t('Month by month')}>
          <table className="table">
            <thead><tr><th>{t('Month')}</th>{ids.map((id) => <th key={id} className="amount">{names[id]}</th>)}<th className="amount">{t('Interest')}</th><th className="amount">{t('Still owing')}</th></tr></thead>
            <tbody>
              {schedule.map((m) => (
                <tr key={m.month}>
                  <td className="num">{monthLabel(m.month)}</td>
                  {ids.map((id) => (
                    <td key={id} className="amount" style={{ fontWeight: 500 }}>
                      {m.payments[id] ? money(m.payments[id], cur) : <span className="muted">—</span>}
                      {plan[pick].paid_off[id] === m.month && <div><span className="pill green">{t('Paid off')}</span></div>}
                    </td>
                  ))}
                  <td className="amount muted" style={{ fontWeight: 500 }}>{money(Object.values(m.interest).reduce((s, v) => s + v, 0), cur)}</td>
                  <td className="amount">{money(m.total_balance, cur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function Strategy({ icon: Icon, title, blurb, r, withExtra, extra, names, currency, best }) {
  const sooner = withExtra?.feasible ? r.months - withExtra.months : 0
  const saved = withExtra?.feasible ? r.total_interest - withExtra.total_interest : 0
  return (
    <section className={`card strategy ${best ? 'best' : ''}`}>
      <div className="card-head">
        <div><h2 className="row" style={{ gap: 8 }}><Icon size={16} className="strategy-icon" aria-hidden="true" />{title}</h2><div className="sub">{blurb}</div></div>
        {best && <span className="pill green">{t('Least interest')}</span>}
      </div>
      <div className="card-body">
        <div className="figures">
          <div className="figure"><div className="label">{t('Debt-free by')}</div><div className="value">{monthLabel(r.payoff_month)}</div><div className="foot">{duration(r.months)}</div></div>
          <div className="figure"><div className="label">{t('Total interest')}</div><div className="value expense"><Money value={r.total_interest} currency={currency} /></div><div className="foot">{t('{amount} paid in all', { amount: money(r.total_paid, currency) })}</div></div>
        </div>
        {extra > 0 && withExtra && (
          <div className="what-if">
            {withExtra.feasible
              ? t('With {extra} more a month: debt-free by {date}, {sooner} sooner, and {saved} less interest.', { extra: money(extra, currency), date: monthLabel(withExtra.payoff_month), sooner: duration(Math.max(0, sooner)), saved: money(saved, currency) })
              : t('Still not enough to pay these off.')}
          </div>
        )}
        <ol className="payoff-order">
          {r.order.map((id) => <li key={id}><span>{names[id]}</span><span className="muted small">{monthLabel(r.paid_off[id])}</span></li>)}
        </ol>
      </div>
    </section>
  )
}

function DebtTip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="t">{monthLabel(label)}</div>
      {payload.map((p) => <div key={p.dataKey} style={{ color: p.color }}>{p.name}: {money(p.value, currency)}</div>)}
    </div>
  )
}
