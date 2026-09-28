import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, Check, Clock, Inbox, Sparkles, Upload } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Empty, ErrorNote, Loading, Money, Progress, useData, useToast, Warnings } from '../components/ui'
import { CategorySelect } from '../components/TxDialog'
import Postmark from '../components/Postmark'
import { AiChip, useAiReady, useAiSuggestions } from '../components/AiTools'
import LowBalanceBanner from '../components/LowBalanceBanner'
import { addMonths, date, money, monthLabel, shortMonth, todayISO } from '../lib/format'

const thisMonth = () => todayISO().slice(0, 7)

export default function Dashboard() {
  const { user, version, bump } = useApp()
  const [month, setMonth] = useState(thisMonth)
  const [flash, setFlash] = useState(null)
  const { data, error, loading } = useData(() => api.get(`/reports/dashboard${qs({ month })}`), [month, version])
  const tray = useData(() => api.get(`/transactions${qs({ uncategorized: true, page_size: 25 })}`), [version])
  const cats = useData(() => api.get('/categories'), [version])
  const batches = useData(() => api.get('/imports/batches'), [version])
  const goals = useData(() => api.get('/goals'), [version])

  if (error) return <ErrorNote error={error} />
  if (!data) return <Loading rows={6} />
  if (data.accounts.length === 0) return <Welcome />
  const cur = data.currency
  const isCurrent = month === thisMonth()
  const lastImport = batches.data?.[0]

  const onSorted = (categoryId) => {
    setFlash(categoryId)
    setTimeout(() => setFlash(null), 1100)
    bump()
  }

  return (
    <div className="stack" aria-busy={loading}>
      <div className="dash-head">
        <div className="dash-title">
          <h1>{monthLabel(month)}</h1>
          {lastImport && (
            <span className="last-stamp" title={t('Most recent import')}>
              <Postmark className="postmark mini" top={lastImport.account_name} date={lastImport.created_at} />
              {t('Last statement in {date}', { date: date(lastImport.created_at, { month: 'short', day: 'numeric' }) })}
            </span>
          )}
        </div>
        <Link to="/import" className="btn primary"><Upload />{t('Import statement')}</Link>
      </div>
      <MonthPockets month={month} onChange={setMonth} />

      <Warnings items={data.warnings} />
      {isCurrent && <LowBalanceBanner />}
      {data.stale_accounts.length > 0 && isCurrent && (
        <div className="banner info">
          <Clock />
          <div className="banner-body">
            <strong>{t('Time for this month\'s statements.')}</strong>{' '}
            {data.stale_accounts.length === 1
              ? t('{names} has nothing newer than {date}.', { names: data.stale_accounts.map((a) => a.name).join(', '), date: date(data.stale_accounts[0].last) })
              : t('{names} have nothing newer than {date}.', { names: data.stale_accounts.map((a) => a.name).join(', '), date: date(data.stale_accounts[0].last) })} <Link to="/import">{t('Import a statement')}</Link>
          </div>
        </div>
      )}

      <div className="sorting">
        <Tray items={tray.data?.items ?? []} total={tray.data?.total ?? 0} cats={cats.data ?? []} onSorted={onSorted} />
        <Wall spending={data.spending} budgets={data.budgets.items} currency={cur} month={month} flash={flash} />
      </div>

      <div className="received-row">
        <section className="received">
          <div className="row" style={{ marginBottom: 10 }}><h2>{t('Recently imported')}</h2><span className="spacer" /><Link to="/import" className="small">{t('All imports')}</Link></div>
          {!batches.data?.length ? <p className="muted small">{t('Nothing imported yet.')}</p> : (
            <div className="postmarks">
              {batches.data.slice(0, 4).map((b) => (
                <Link key={b.id} to={`/transactions?account=${b.account_id}`} className="envelope">
                  <Postmark top={b.account_name} date={b.created_at} />
                  <div style={{ minWidth: 0 }}>
                    <div className="who">{b.account_name}</div>
                    <small>{b.skipped ? t('{n} added, {skipped} already here', { n: b.imported, skipped: b.skipped }) : t('{n} added', { n: b.imported })}</small>
                    <small>{date(b.created_at, { month: 'short', day: 'numeric' })} · {b.format.startsWith('sync') ? t('bank sync') : b.format.toUpperCase()}</small>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
        <MonthTotals data={data} currency={cur} month={month} />
      </div>

      <div className="grid-2">
        <BalanceFlow flow={data.balance_flow} currency={cur} month={month} />
        <section className="card">
          <div className="card-head"><h2>{t('Savings goals')}</h2><Link to="/goals" className="small">{t('All goals')}</Link></div>
          {!goals.data?.length ? (
            <Empty title={t('No goals yet')} action={<Link to="/goals" className="btn sm">{t('Add a goal')}</Link>}>{t('Set a target, like an emergency fund, and track it here.')}</Empty>
          ) : (
            <div className="list">
              {goals.data.slice(0, 4).map((g) => (
                <div className="list-row" key={g.id} style={{ display: 'block' }}>
                  <div className="row"><span className="title">{g.name}</span><span className="spacer" />
                    <span className="small"><Money value={g.saved} currency={g.currency} className="strong" /> <span className="muted">{t('of')}</span> <Money value={g.target_amount} currency={g.currency} /></span></div>
                  <div className="row" style={{ marginTop: 7 }}><div style={{ flex: 1 }}><Progress thick value={g.percent} color="var(--post)" /></div><span className="small strong" style={{ width: 40, textAlign: 'right' }}>{Math.round(g.percent ?? 0)}%</span></div>
                  {g.monthly_needed != null && <div className="meta" style={{ marginTop: 4 }}><Money value={g.monthly_needed} currency={g.currency} /> {t('a month reaches it by {date}', { date: date(g.target_date) })}</div>}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

// Month pockets: the last six months as tabs, like the dividers of an accordion file.
function MonthPockets({ month, onChange }) {
  const now = thisMonth()
  const months = Array.from({ length: 6 }, (_, i) => addMonths(now, i - 5))
  if (!months.includes(month)) months.unshift(month)
  return (
    <div className="pockets" role="tablist" aria-label={t('Month')}>
      {months.map((m) => (
        <button key={m} role="tab" aria-selected={m === month} className={m === month ? 'on' : ''} onClick={() => onChange(m)}>
          {shortMonth(m)}{m.slice(0, 4) !== now.slice(0, 4) ? ` ${m.slice(2, 4)}` : ''}
        </button>
      ))}
      <button className="pocket-older" onClick={() => onChange(addMonths(months[0], -1))} title={t('Go back another month')}>{t('Earlier')}</button>
    </div>
  )
}

function MonthTotals({ data, currency, month }) {
  const m = data.this_month
  return (
    <section className="card totals">
      <div className="card-head"><h2>{t('{month} in numbers', { month: monthLabel(month).split(' ')[0] })}</h2></div>
      <dl>
        <div><dt>{t('Money in')}</dt><dd className="income"><Money value={m.income} currency={currency} /></dd></div>
        <div><dt>{t('Money out')}</dt><dd className="expense"><Money value={m.expense} currency={currency} /></dd></div>
        <div><dt>{t('Kept')}</dt><dd><Money value={m.net} currency={currency} sign />{m.savings_rate != null && <span className="muted small"> · <span className="money-v">{Math.round(m.savings_rate)}%</span></span>}</dd></div>
        <div className="sep"><dt>{t('In your accounts')}</dt><dd><Money value={data.total_balance} currency={currency} /></dd></div>
        <div><dt>{t('Net worth')}</dt><dd><Money value={data.net_worth.current.net} currency={currency} /></dd></div>
      </dl>
    </section>
  )
}

// The "to sort" tray: uncategorized lines with suggested categories, sorted in one click.
function Tray({ items, total, cats, onSorted }) {
  const toast = useToast()
  const [leaving, setLeaving] = useState(new Set())
  const aiReady = useAiReady()
  const ai = useAiSuggestions(items.map((tx) => tx.id), aiReady)
  const byId = useMemo(() => Object.fromEntries(cats.map((c) => [c.id, c])), [cats])
  const fallback = useMemo(() => {
    const top = (k) => cats.filter((c) => c.kind === k).sort((a, b) => b.transaction_count - a.transaction_count).map((c) => c.id)
    return { expense: top('expense'), income: top('income') }
  }, [cats])

  const sort = async (tx, categoryId) => {
    if (!categoryId) return
    setLeaving((s) => new Set(s).add(tx.id))
    try {
      await api.patch(`/transactions/${tx.id}`, { category_id: categoryId })
      setTimeout(() => onSorted(categoryId), 340)
    } catch (e) {
      toast(e.message, 'error')
      setLeaving((s) => { const n = new Set(s); n.delete(tx.id); return n })
    }
  }

  return (
    <section className="tray" aria-label={t('Transactions to sort')}>
      <div className="tray-head"><Inbox size={18} /><div><h2>{t('To sort')}</h2><div className="tray-sub">{t('New lines without a category')}</div></div><span className="count">{total}</span></div>
      {items.length === 0 ? (
        <div className="tray-empty"><Check size={22} style={{ color: 'var(--green)' }} /><div className="strong" style={{ color: 'var(--ink)', marginTop: 6 }}>{t('All sorted')}</div><div className="small">{t('Every transaction has a category.')}</div></div>
      ) : (
        <div className="tray-body">
          {aiReady && (ai.missing > 0 || ai.error) && (
            <div className="ai-tray-ask">
              <button className="btn ghost sm" onClick={ai.ask} disabled={ai.busy}><Sparkles />{ai.busy ? t('Asking…') : t('Suggest with AI')}</button>
              {ai.error && <span className="small expense">{ai.error.message}</span>}
            </div>
          )}
          {items.map((tx) => {
            const aiPick = ai.map[tx.id]
            const picks = [...new Set([...(tx.suggestions ?? []), ...(tx.amount < 0 ? fallback.expense : fallback.income)])].filter((id) => byId[id] && id !== aiPick?.category_id).slice(0, aiPick ? 1 : 2)
            return (
              <div key={tx.id} className={`tray-item ${leaving.has(tx.id) ? 'sorted' : ''}`}>
                <div className="top"><span className="desc" title={tx.description}>{tx.description}</span><Money value={tx.amount} currency={tx.currency} sign colored className="strong" /></div>
                <div className="when">{date(tx.date, { month: 'short', day: 'numeric' })} · {tx.account_name}</div>
                <div className="sort-row">
                  {aiPick && <AiChip s={aiPick} onAccept={() => sort(tx, aiPick.category_id)} onReject={() => ai.reject(aiPick)} />}
                  {picks.map((id, i) => {
                    const likely = i === 0 && tx.suggestions?.[0] === id
                    return <button key={id} className={`sort-chip ${likely ? 'likely' : ''}`} onClick={() => sort(tx, id)} style={{ '--c': byId[id].color }} title={likely ? t('Where this merchant usually goes') : undefined}><i />{byId[id].name}</button>
                  })}
                  <CategorySelect className="sort-other" categories={cats} value={null} placeholder={t('Other…')} onChange={(v) => sort(tx, v)} aria-label={t('Category for {name}', { name: tx.description })} />
                </div>
              </div>
            )
          })}
          {total > items.length && <Link to="/transactions?uncategorized=1" className="tray-empty" style={{ display: 'block', padding: 14 }}>{t('{n} more to sort', { n: total - items.length })} <ArrowRight size={14} style={{ verticalAlign: -2 }} /></Link>}
        </div>
      )}
    </section>
  )
}

// "Where it went": one box per spending category; its pocket fills toward the monthly limit.
function Wall({ spending, budgets, currency, month, flash }) {
  const cells = useMemo(() => {
    const byId = new Map()
    for (const s of spending) if (s.category_id) byId.set(s.category_id, { id: s.category_id, name: s.name, color: s.color, spent: s.total, budget: s.budget })
    for (const b of budgets) if (!byId.has(b.category_id)) byId.set(b.category_id, { id: b.category_id, name: b.name, color: b.color, spent: 0, budget: b.budget })
    return [...byId.values()]
      .map((c) => ({ ...c, pct: c.budget ? c.spent / c.budget : null, over: c.budget != null && c.spent > c.budget }))
      .sort((a, b) => (b.budget != null) - (a.budget != null) || b.spent - a.spent)
  }, [spending, budgets])

  return (
    <section className="wall-wrap" aria-label={t('Spending by category')}>
      <div className="wall-head"><div><h2>{t('Where it went')}</h2><div className="sub">{t('Each pocket fills up toward its monthly limit')}</div></div><Link to="/budgets" className="small">{t('Set limits')}</Link></div>
      {cells.length === 0 ? (
        <div className="hole" style={{ minHeight: 120, placeItems: 'center', display: 'grid', color: 'var(--ink-3)' }}>{t('Nothing sorted this month yet.')}</div>
      ) : (
        <div className="wall">
          {cells.map((c) => (
            <Link key={c.id} to={`/transactions?category=${c.id}&month=${month}`} className={`hole ${c.over ? 'over' : ''} ${flash === c.id ? 'flash' : ''}`} style={{ '--c': c.color }}>
              <div className="hole-label"><i />{c.name}</div>
              <div className="hole-body">
                <div className="amt"><Money value={c.spent} currency={currency} /></div>
                <div className="of">{c.budget != null ? <>{t('of')} <Money value={c.budget} currency={currency} /></> : t('no limit set')}{c.over && <span className="band">{t('over by')} <Money value={c.spent - c.budget} currency={currency} compact /></span>}</div>
              </div>
              <div className={`slot ${c.pct == null ? 'open' : ''}`} aria-hidden="true">
                {c.pct != null && <span style={{ transform: `scaleY(${Math.min(1, c.pct)})` }} />}
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function BalanceFlow({ flow, currency, month }) {
  return (
    <section className="card chart-card">
      <div className="card-head" style={{ alignItems: 'flex-start' }}>
        <div><h2>{t('Balance through the month')}</h2><div className="sub">{t('{start} to {end}. Dotted line is last month.', { start: date(flow.start, { month: 'short', day: 'numeric' }), end: date(flow.end, { month: 'short', day: 'numeric' }) })}</div></div>
        <div className={`strong ${flow.change >= 0 ? 'income' : 'expense'}`} style={{ fontSize: 19 }}><Money value={flow.change} currency={currency} sign /></div>
      </div>
      <div style={{ height: 260, padding: '12px 12px 4px 0' }}>
        <ResponsiveContainer>
          <AreaChart data={flow.series} margin={{ left: 8, right: 8, top: 6 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="day" tickLine={false} axisLine={false} interval={3} />
            <YAxis tickLine={false} axisLine={false} width={62} domain={[(min) => Math.floor(min - Math.abs(min) * 0.03), (max) => Math.ceil(max + Math.abs(max) * 0.02)]} tickFormatter={(v) => money(v, currency, { compact: true })} />
            <Tooltip content={<FlowTip currency={currency} month={month} />} cursor={{ stroke: 'var(--rule-2)' }} />
            <Line dataKey="previous" stroke="var(--post)" strokeDasharray="3 4" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <Area dataKey="current" stroke="var(--frame)" fill="var(--frame)" fillOpacity={0.1} strokeWidth={2.2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function FlowTip({ active, payload, label, currency, month }) {
  if (!active || !payload?.length) return null
  const cur = payload.find((p) => p.dataKey === 'current')?.value
  const prev = payload.find((p) => p.dataKey === 'previous')?.value
  return (
    <div className="chart-tip">
      <div className="t">{t('Day {n}', { n: label })}</div>
      {cur != null && <div>{monthLabel(month).split(' ')[0]}: <strong>{money(cur, currency)}</strong></div>}
      {prev != null && <div style={{ color: 'var(--post)' }}>{monthLabel(addMonths(month, -1)).split(' ')[0]}: {money(prev, currency)}</div>}
    </div>
  )
}

function Welcome() {
  const steps = [
    { t: t('Add your accounts'), d: t('Chequing, savings, credit cards. Pick the bank so imports know the file layout.'), to: '/accounts', a: t('Add an account') },
    { t: t('Import a statement'), d: t('Download QFX/OFX (best), CSV or a text-based PDF from online banking. Your bank password never touches FinVault.'), to: '/import', a: t('Import a file') },
    { t: t('Sort what arrives'), d: t('Give each new line a category. Rules and remembered merchants sort repeat purchases for you after that.'), to: '/rules', a: t('Set up rules') },
  ]
  return (
    <div className="stack">
      <div className="dash-head"><div className="dash-title"><h1>{t('Let\'s set up your books')}</h1></div></div>
      <div className="wall-wrap">
        <div className="wall" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          {steps.map((s, i) => (
            <div key={s.t} className="hole" style={{ '--c': 'var(--tray)', minHeight: 200 }}>
              <div className="hole-label"><i />{t('Step {n}', { n: i + 1 })}</div>
              <div className="hole-body" style={{ marginTop: 8 }}>
                <h3 style={{ marginBottom: 6 }}>{s.t}</h3>
                <p className="small" style={{ color: 'var(--ink-2)', marginBottom: 12 }}>{s.d}</p>
                <Link to={s.to} className="btn sm">{i === 1 && <Upload />}{s.a}</Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
