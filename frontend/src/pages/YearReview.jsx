import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowDownRight, ArrowUpRight, FileDown, Gift, Landmark, Repeat, ShoppingBag, Store } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { CategoryTile, ChartTable, Empty, ErrorNote, Loading, Money, useData, usePageTitle, Warnings } from '../components/ui'
import { date, money, monthLabel, shortMonth, todayISO } from '../lib/format'

export default function YearReview() {
  const { version } = useApp()
  const now = new Date()
  // Early in the year, last year is the one worth reviewing.
  const [year, setYear] = useState(now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear())
  const r = useData(() => api.get(`/reports/year-review${qs({ year })}`), [year, version])
  usePageTitle(t('Year in review'))

  const first = r.data?.first_year ?? now.getFullYear()
  const years = []
  for (let y = now.getFullYear(); y >= Math.min(first, year); y--) years.push(y)

  return (
    <div className="yir">
      <header className="yir-hero">
        <div>
          <h1>{t('Your {year}, in money', { year })}</h1>
          {r.data && <p className="sub">{r.data.partial ? t('So far this year, through {date}.', { date: date(r.data.through) }) : t('January 1 to December 31, {year}.', { year })}</p>}
        </div>
        <div className="page-actions no-print">
          <select className="input" style={{ width: 120 }} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label={t('Year')}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button className="btn primary" onClick={() => window.print()}><FileDown />{t('Export PDF')}</button>
        </div>
      </header>
      {r.error ? <ErrorNote error={r.error} /> : !r.data ? <Loading rows={8} /> : r.data.transaction_count === 0 ? (
        <div className="card"><Empty icon={Gift} title={t('Nothing recorded in {year}', { year })}>{t('Import statements from that year and your review fills itself in.')}</Empty></div>
      ) : <Review d={r.data} />}
    </div>
  )
}

function Change({ value, pct, invert, currency }) {
  if (value == null || Math.abs(value) < 0.005) return <span className="muted small">{t('same as last year')}</span>
  const up = value > 0
  const good = invert ? !up : up
  return (
    <span className={`yir-change ${good ? 'good' : 'bad'}`}>
      {up ? <ArrowUpRight /> : <ArrowDownRight />}
      <Money value={Math.abs(value)} currency={currency} />{pct != null && <span className="money-v"> ({Math.abs(Math.round(pct))}%)</span>}
    </span>
  )
}

function Review({ d }) {
  const c = d.currency
  const tot = d.totals
  const prev = d.last_year_totals
  const biggest = new Set(d.biggest_months.map((m) => m.month))
  const cats = d.categories.slice(0, 10)
  const maxCat = Math.max(1, ...cats.map((x) => Math.max(x.total, x.last_year)))
  const registered = d.registered.filter((p) => p.contributed || p.withdrawn)

  return (
    <div className="stack">
      <Warnings items={d.warnings} />

      <section className="manifest yir-manifest">
        <div><div className="label">{t('Money in')}</div><div className="value income"><Money value={tot.income} currency={c} /></div><div className="foot">{prev.income ? <Change value={tot.income - prev.income} currency={c} /> : t('no data for last year')}</div></div>
        <div><div className="label">{t('Money out')}</div><div className="value expense"><Money value={tot.expense} currency={c} /></div><div className="foot">{prev.expense ? <Change value={tot.expense - prev.expense} invert currency={c} /> : t('no data for last year')}</div></div>
        <div><div className="label">{t('Savings rate')}</div><div className="value">{tot.savings_rate == null ? '—' : <span className="money-v">{tot.savings_rate}%</span>}</div><div className="foot">{t('kept {amount}', { amount: money(tot.net, c) })}</div></div>
        <div><div className="label">{t('Net worth change')}</div><div className={`value ${d.net_worth.change >= 0 ? 'income' : 'expense'}`}><Money value={d.net_worth.change} currency={c} sign /></div><div className="foot">{t('now {amount}', { amount: money(d.net_worth.end, c) })}</div></div>
        <div><div className="label">{t('Subscriptions')}</div><div className="value"><Money value={d.subscriptions.total} currency={c} /></div><div className="foot">{d.subscriptions.has_category ? t('about {amount} a month', { amount: money(d.subscriptions.total / 12, c) }) : t('no Subscriptions category')}</div></div>
      </section>

      <section className="card chart-card yir-block">
        <div className="card-head">
          <div><h2>{t('Month by month')}</h2><div className="sub">{d.biggest_months.length ? t('Your biggest spending months were {months}.', { months: d.biggest_months.map((m) => monthLabel(m.month).split(' ')[0]).join(', ') }) : ''}{d.best_month && d.best_month.net > 0 ? ` ${t('You kept the most in {month}.', { month: monthLabel(d.best_month.month).split(' ')[0] })}` : ''}</div></div>
          <div className="legend"><span><i className="dot" style={{ '--dot': 'var(--income)' }} />{t('Money in')}</span><span><i className="dot" style={{ '--dot': 'var(--expense)' }} />{t('Money out')}</span></div>
        </div>
        <div style={{ height: 280, padding: '14px 12px 4px 0' }}>
          <ResponsiveContainer>
            <BarChart data={d.months} margin={{ left: 8, right: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickFormatter={shortMonth} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => money(v, c, { compact: true })} tickLine={false} axisLine={false} width={64} />
              <Tooltip content={<MonthTip currency={c} />} cursor={{ fill: 'var(--sheet-2)' }} />
              <Bar dataKey="income" name={t('Money in')} fill="var(--income)" fillOpacity={0.55} radius={[5, 5, 0, 0]} maxBarSize={24} isAnimationActive={false} />
              <Bar dataKey="expense" name={t('Money out')} radius={[5, 5, 0, 0]} maxBarSize={24} isAnimationActive={false}>
                {d.months.map((m) => <Cell key={m.month} fill="var(--expense)" fillOpacity={biggest.has(m.month) ? 1 : 0.55} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ChartTable caption={t('Month by month')} columns={[t('Month'), t('Money in'), t('Money out')]}
          rows={d.months.map((m) => [monthLabel(m.month), money(m.income, c), money(m.expense, c)])} />
      </section>

      <section className="card yir-block">
        <div className="card-head"><div><h2>{t('Where it went')}</h2><div className="sub">{t('Spending by category, this year against last year.')}</div></div>
          <div className="legend"><span><i className="dot" style={{ '--dot': 'var(--ink-3)' }} />{d.year}</span><span><i className="dot" style={{ '--dot': 'var(--rule-2)' }} />{d.year - 1}</span></div>
        </div>
        {!cats.length ? <Empty title={t('No spending recorded')} /> : (
          <div className="list">
            {cats.map((x) => (
              <div className="cat-row" key={x.category_id ?? 'none'}>
                <CategoryTile size="sm" name={x.name} color={x.color} />
                <div className="grow">
                  <div className="line"><span className="name">{x.name}</span><Money value={x.total} currency={c} className="strong" /></div>
                  <div className="yir-bars" aria-hidden="true">
                    <span style={{ width: `${(x.total / maxCat) * 100}%`, '--bar': x.color }} />
                    <span className="last" style={{ width: `${(x.last_year / maxCat) * 100}%` }} />
                  </div>
                  <div className="meta small">{x.last_year ? <>{t('{amount} last year', { amount: money(x.last_year, c) })} · <Change value={x.change} pct={x.change_pct} invert currency={c} /></> : <span className="muted">{t('new this year')}</span>}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid-2">
        <section className="card yir-block">
          <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Store size={16} />{t('Top merchants')}</h2></div>
          {!d.top_merchants.length ? <Empty title={t('No purchases recorded')} /> : (
            <ol className="yir-rank">
              {d.top_merchants.map((m, i) => (
                <li key={m.name + i}><span className="rank">{i + 1}</span><span className="grow"><span className="title">{m.name}</span><span className="meta">{t(m.count === 1 ? '{n} visit' : '{n} visits', { n: m.count })}</span></span><Money value={m.total} currency={c} className="strong" /></li>
              ))}
            </ol>
          )}
        </section>
        <section className="card yir-block">
          <div className="card-head"><h2 className="row" style={{ gap: 8 }}><ShoppingBag size={16} />{t('Largest single purchases')}</h2></div>
          {!d.largest_purchases.length ? <Empty title={t('No purchases recorded')} /> : (
            <ol className="yir-rank">
              {d.largest_purchases.map((p, i) => (
                <li key={p.id}><span className="rank">{i + 1}</span><span className="grow"><span className="title">{p.description}</span><span className="meta">{date(p.date, { month: 'short', day: 'numeric' })}{p.category ? ` · ${p.category}` : ''}</span></span><Money value={p.amount} currency={c} className="strong" /></li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <div className="grid-2">
        <section className="card yir-block">
          <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Landmark size={16} />{t('Saved in registered accounts')}</h2></div>
          <div className="card-body">
            {!registered.length ? <p className="muted small">{t('No TFSA, RRSP or FHSA contributions recorded for {year}. Add them on the Registered accounts page.', { year: d.year })}</p> : (
              <div className="figures">
                {registered.map((p) => (
                  <div className="figure" key={p.kind}>
                    <div className="label">{t(p.label)}</div>
                    <div className="value"><Money value={p.contributed} currency="CAD" /></div>
                    <div className="foot">{p.withdrawn > 0 ? t('{amount} taken out', { amount: money(p.withdrawn, 'CAD') }) : t('of {amount} room', { amount: money(p.room, 'CAD') })}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
        <section className="card yir-block yir-note">
          <div className="card-head"><h2 className="row" style={{ gap: 8 }}><Repeat size={16} />{t('The year in a sentence')}</h2></div>
          <div className="card-body">
            <p>{tot.net >= 0
              ? t('You brought in {income}, spent {expense}, and kept {net}: {rate}% of what came in.', { income: money(tot.income, c), expense: money(tot.expense, c), net: money(tot.net, c), rate: tot.savings_rate ?? 0 })
              : t('You brought in {income} and spent {expense}, {net} more than came in.', { income: money(tot.income, c), expense: money(tot.expense, c), net: money(-tot.net, c) })}</p>
            <p className="small muted">{t('Split transactions and shared costs count only your part. Transfers between your own accounts are left out.')}</p>
          </div>
        </section>
      </div>
      <p className="small muted print-only">{t('Printed from FinVault on {date}.', { date: date(todayISO()) })}</p>
    </div>
  )
}

function MonthTip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="t">{monthLabel(label)}</div>
      {payload.map((p) => <div key={p.dataKey}>{p.name}: {money(p.value, currency)}</div>)}
    </div>
  )
}
