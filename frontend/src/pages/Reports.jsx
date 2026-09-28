import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, ComposedChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, qs } from '../api'
import { useApp } from '../context'
import { CategoryTile, Empty, Loading, Money, PageHead, Progress, useData, Warnings } from '../components/ui'
import { money, monthLabel, shortMonth } from '../lib/format'
import { t } from '../i18n'

const RANGES = [[3, '3 months'], [6, '6 months'], [12, '12 months'], [24, '2 years']]

function rangeStart(months) {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - (months - 1))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

export default function Reports() {
  const { version } = useApp()
  const [tab, setTab] = useState('ie')
  const [months, setMonths] = useState(12)
  const ie = useData(() => api.get(`/reports/income-expense${qs({ start: rangeStart(months) })}`), [months, version])
  const nw = useData(() => api.get(`/reports/net-worth${qs({ months })}`), [months, version])

  return (
    <>
      <PageHead title={t('Reports')}>
        <div className="segmented">
          <button className={tab === 'ie' ? 'on' : ''} onClick={() => setTab('ie')}>{t('Income vs expenses')}</button>
          <button className={tab === 'nw' ? 'on' : ''} onClick={() => setTab('nw')}>{t('Net worth')}</button>
          <button className={tab === 'cat' ? 'on' : ''} onClick={() => setTab('cat')}>{t('Categories')}</button>
        </div>
        <select className="input" style={{ width: 140 }} value={months} onChange={(e) => setMonths(Number(e.target.value))} aria-label={t('Range')}>
          {RANGES.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
        </select>
      </PageHead>
      {tab === 'nw' ? <NetWorth r={nw} /> : !ie.data ? <Loading rows={6} /> : tab === 'ie' ? <IncomeExpense d={ie.data} /> : <CategoryReport d={ie.data} />}
    </>
  )
}

function Tip({ active, payload, label, currency, fmtLabel = monthLabel }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="t">{fmtLabel(label)}</div>
      {payload.map((p) => <div key={p.dataKey} style={{ color: p.color }}>{t('{label}:', { label: p.name })} {money(p.value, currency)}</div>)}
    </div>
  )
}

function IncomeExpense({ d }) {
  const c = d.currency
  const totals = d.totals
  const avg = (k) => d.series.length ? d.series.reduce((s, x) => s + x[k], 0) / d.series.length : 0
  return (
    <div className="stack">
      <Warnings items={d.warnings} />
      <section className="card summary" style={{ gridTemplateColumns: '1fr' }}>
        <div className="summary-main">
          <div className="figures">
            <div className="figure"><div className="label">{t('Income')}</div><div className="value income"><Money value={totals.income} currency={c} /></div><div className="foot">{t('avg')} <Money value={avg('income')} currency={c} />{t('/mo')}</div></div>
            <div className="figure"><div className="label">{t('Expenses')}</div><div className="value expense"><Money value={totals.expense} currency={c} /></div><div className="foot">{t('avg')} <Money value={avg('expense')} currency={c} />{t('/mo')}</div></div>
            <div className="figure"><div className="label">{t('Net saved')}</div><div className={`value ${totals.net >= 0 ? 'income' : 'expense'}`}><Money value={totals.net} currency={c} sign /></div></div>
            <div className="figure"><div className="label">{t('Savings rate')}</div><div className="value">{totals.savings_rate == null ? '—' : <span className="money-v">{totals.savings_rate}%</span>}</div></div>
          </div>
        </div>
      </section>
      <section className="card chart-card">
        <div className="card-head"><h2>{t('Month by month')}</h2>
          <div className="legend"><span><i className="dot" style={{ '--dot': 'var(--income)' }} />{t('Income')}</span><span><i className="dot" style={{ '--dot': 'var(--expense)' }} />{t('Expenses')}</span><span><i className="dot" style={{ '--dot': 'var(--primary)' }} />{t('Net')}</span></div>
        </div>
        <div style={{ height: 340, padding: '16px 12px 8px 0' }}>
          <ResponsiveContainer>
            <ComposedChart data={d.series} margin={{ left: 8, right: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickFormatter={shortMonth} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => money(v, c, { compact: true })} tickLine={false} axisLine={false} width={64} />
              <Tooltip content={<Tip currency={c} />} cursor={{ fill: 'var(--muted)' }} />
              <Bar dataKey="income" name={t('Income')} fill="var(--income)" radius={[5, 5, 0, 0]} maxBarSize={28} />
              <Bar dataKey="expense" name={t('Expenses')} fill="var(--expense)" radius={[5, 5, 0, 0]} maxBarSize={28} />
              <Line dataKey="net" name={t('Net')} stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>
      <div className="grid-2">
        <Breakdown title={t('Where the money went')} items={d.expense_by_category} total={totals.expense} currency={c} />
        <Breakdown title={t('Where it came from')} items={d.income_by_category} total={totals.income} currency={c} />
      </div>
    </div>
  )
}

function Breakdown({ title, items, total, currency }) {
  return (
    <section className="card">
      <div className="card-head"><h2>{title}</h2></div>
      {!items.length ? <Empty title={t('Nothing in this range')} /> : (
        <div className="list">
          {items.slice(0, 10).map((i) => (
            <Link key={i.category_id ?? 'none'} to={i.category_id ? `/transactions?category=${i.category_id}` : '/transactions?uncategorized=1'} className="cat-row" style={{ color: 'inherit', textDecoration: 'none' }}>
              <CategoryTile size="sm" name={i.name} color={i.color} />
              <div className="grow">
                <div className="line"><span className="name">{i.name}</span><Money value={i.total} currency={currency} className="strong" /></div>
                <div className="budget-line"><Progress value={(i.total / total) * 100} color={i.color} /><span className="small muted num" style={{ width: 40, textAlign: 'right' }}>{Math.round((i.total / total) * 100)}%</span></div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function CategoryReport({ d }) {
  const c = d.currency
  const data = d.expense_by_category.slice(0, 12)
  return (
    <div className="stack">
      <Warnings items={d.warnings} />
      <div className="grid-2">
        <section className="card chart-card">
          <div className="card-head"><h2>{t('Spending share')}</h2></div>
          {!data.length ? <Empty title={t('No spending in this range')} /> : (
            <div style={{ height: 360 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={data} dataKey="total" nameKey="name" innerRadius="55%" outerRadius="85%" paddingAngle={2} stroke="var(--card)" strokeWidth={2}>
                    {data.map((x) => <Cell key={x.name} fill={x.color} />)}
                  </Pie>
                  <Tooltip formatter={(v) => money(v, c)} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 9 }} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
        <Breakdown title={t('Top categories')} items={d.expense_by_category} total={d.totals.expense} currency={c} />
      </div>
    </div>
  )
}

function NetWorth({ r }) {
  if (!r.data) return <Loading rows={6} />
  const d = r.data
  const c = d.currency
  if (d.series.every((s) => s.net === 0 && s.assets === 0)) return <Empty title={t('Nothing to chart yet')}>{t('Add accounts and assets to see your net worth over time.')}</Empty>
  return (
    <div className="stack">
      <Warnings items={d.warnings} />
      <section className="card summary" style={{ gridTemplateColumns: '1fr' }}>
        <div className="summary-main">
          <div className="figures">
            <div className="figure"><div className="label">{t('Net worth')}</div><div className="value" style={{ fontSize: 28 }}><Money value={d.current.net} currency={c} /></div>
              {d.change != null && <div className="foot"><Money value={d.change} currency={c} sign colored /> {t('this month')}</div>}</div>
            <div className="figure"><div className="label">{t('Assets')}</div><div className="value income"><Money value={d.current.assets} currency={c} /></div></div>
            <div className="figure"><div className="label">{t('Liabilities')}</div><div className="value expense"><Money value={-d.current.liabilities} currency={c} /></div></div>
          </div>
        </div>
      </section>
      <section className="card chart-card">
        <div className="card-head"><h2>{t('Net worth over time')}</h2></div>
        <div style={{ height: 340, padding: '16px 12px 8px 0' }}>
          <ResponsiveContainer>
            <AreaChart data={d.series} margin={{ left: 8, right: 8 }}>
              <defs><linearGradient id="nw" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--primary)" stopOpacity={0.18} /><stop offset="1" stopColor="var(--primary)" stopOpacity={0.01} /></linearGradient></defs>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickFormatter={shortMonth} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => money(v, c, { compact: true })} tickLine={false} axisLine={false} width={64} />
              <Tooltip content={<Tip currency={c} />} />
              <Area dataKey="net" name={t('Net worth')} stroke="var(--primary)" fill="url(#nw)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="card chart-card">
        <div className="card-head"><h2>{t('Assets and liabilities')}</h2></div>
        <div style={{ height: 280, padding: '16px 12px 8px 0' }}>
          <ResponsiveContainer>
            <BarChart data={d.series.map((s) => ({ ...s, liabilities: -s.liabilities }))} stackOffset="sign" margin={{ left: 8, right: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickFormatter={shortMonth} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => money(v, c, { compact: true })} tickLine={false} axisLine={false} width={64} />
              <Tooltip content={<Tip currency={c} />} cursor={{ fill: 'var(--muted)' }} />
              <Bar dataKey="assets" name={t('Assets')} fill="var(--income)" stackId="s" radius={[5, 5, 0, 0]} maxBarSize={30} />
              <Bar dataKey="liabilities" name={t('Liabilities')} fill="var(--expense)" stackId="s" radius={[0, 0, 5, 5]} maxBarSize={30} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  )
}
