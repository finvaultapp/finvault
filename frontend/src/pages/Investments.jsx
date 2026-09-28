import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Calculator, Clock, LineChart, Pencil, Plus, RefreshCw, Tag, Trash2, Undo2, Upload } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api'
import { useApp } from '../context'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { CURRENCIES, date, money, todayISO } from '../lib/format'
import { t } from '../i18n'

// English labels are the i18n keys; they translate at render.
// Allocation is neither money in nor out, so the donuts use the neutral data palette (styles.css --data-*), not the lamps.
// Slices take the palette in order, so neighbouring slices never share a colour.
const CLASSES = {
  equity: 'Equities', fixed_income: 'Bonds and fixed income', cash: 'Cash', balanced: 'Balanced funds',
  real_estate: 'Real estate', commodity: 'Commodities', crypto: 'Crypto', other: 'Other',
}
const DATA_COLORS = ['var(--data-1)', 'var(--data-2)', 'var(--data-3)', 'var(--data-4)', 'var(--data-5)']
const REGISTRATIONS = {
  non_registered: 'Non-registered', tfsa: 'TFSA', rrsp: 'RRSP', fhsa: 'FHSA', resp: 'RESP', rrif: 'RRIF', lira: 'LIRA', other: 'Other registered',
}
const KINDS = {
  buy: 'Buy', sell: 'Sell', dividend: 'Dividend', distribution: 'Distribution', reinvested_dividend: 'Reinvested dividend',
  fee: 'Fee', split: 'Stock split', return_of_capital: 'Return of capital',
}
const SOURCES = {
  auto: 'Detect automatically', wealthsimple_holdings: 'Wealthsimple holdings', wealthsimple_activity: 'Wealthsimple activity',
  wealthsimple_statement: 'Wealthsimple statement', questrade: 'Questrade activity', generic: 'Other activity file (generic)',
  generic_holdings: 'Other holdings file (generic)',
}

function pct(v) {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`
}

function ageLabel(days) {
  if (days === null || days === undefined) return t('no price')
  if (days <= 0) return t('today')
  if (days === 1) return t('1 day old')
  return t('{n} days old', { n: days })
}

export default function Investments() {
  const { version, bump } = useApp()
  const toast = useToast()
  const ov = useData(() => api.get('/invest/overview'), [version])
  const [importing, setImporting] = useState(false)
  const [activity, setActivity] = useState(null)
  const [holding, setHolding] = useState(null)
  const [pricing, setPricing] = useState(null)
  const [security, setSecurity] = useState(null)
  const [fetching, setFetching] = useState(false)

  if (ov.error) return <div className="banner warn"><AlertTriangle /><div className="banner-body">{ov.error.message}</div></div>
  if (!ov.data) return <Loading rows={6} />
  const d = ov.data
  const c = d.base_currency
  const accounts = d.accounts.filter((a) => !a.is_archived || a.positions.length)
  const hasPositions = accounts.some((a) => a.positions.length)

  const fetchPrices = async () => {
    setFetching(true)
    try {
      const r = await api.post('/invest/prices/fetch')
      toast(r.failed.length ? t('Updated {n} prices. No new price for {symbols}; the last one is kept.', { n: r.updated, symbols: r.failed.join(', ') }) : t('Updated {n} prices', { n: r.updated }), r.failed.length ? 'error' : 'ok')
      bump()
    } catch (e) { toast(e.message, 'error') } finally { setFetching(false) }
  }

  return (
    <>
      <PageHead title={t('Investments')} sub={t('Holdings in your TFSA, RRSP, FHSA and non-registered accounts. Account value is the cash balance plus the market value of what you hold.')}>
        {d.prices_fetch_enabled && hasPositions && <button className="btn" onClick={fetchPrices} disabled={fetching}><RefreshCw className={fetching ? 'spin' : ''} />{t('Fetch prices')}</button>}
        <button className="btn" onClick={() => setActivity({})} disabled={!accounts.length}><Plus />{t('Add activity')}</button>
        <button className="btn primary" onClick={() => setImporting(true)} disabled={!accounts.length}><Upload />{t('Import holdings')}</button>
      </PageHead>
      <div className="stack">
        <Warnings items={d.warnings} />
        {d.price_warnings.length > 0 && (
          <div className="banner warn" role="alert"><AlertTriangle />
            <div className="banner-body"><strong>{t('Some holdings have no price yet.')}</strong>{' '}
              {t('{symbols} are counted at book cost until you add a price.', { symbols: d.price_warnings.map((w) => w.symbol).join(', ') })}</div>
          </div>
        )}
        {!accounts.length ? (
          <div className="card"><Empty icon={LineChart} title={t('No investment accounts yet')} action={<Link className="btn primary" to="/accounts"><Plus />{t('Add an investment account')}</Link>}>
            {t('Add an account with the type Investment (your TFSA, RRSP, FHSA or a non-registered account), then import a holdings or activity export.')}
          </Empty></div>
        ) : <>
          <section className="card summary invest-summary">
            <div className="summary-main">
              <div className="figures">
                <div className="figure"><div className="label">{t('Total value')}</div><div className="value" style={{ fontSize: 28 }}><Money value={d.totals.total} currency={c} /></div>
                  <div className="foot">{t('holdings')} <Money value={d.totals.market_value} currency={c} /> · {t('cash')} <Money value={d.totals.cash} currency={c} /></div></div>
                <div className="figure"><div className="label">{t('Book cost')}</div><div className="value"><Money value={d.totals.cost} currency={c} /></div></div>
                <div className="figure"><div className="label">{t('Unrealized gain or loss')}</div>
                  <div className={`value ${d.totals.gain >= 0 ? 'income' : 'expense'}`}><Money value={d.totals.gain} currency={c} sign /></div>
                  <div className="foot">{pct(d.totals.gain_pct)}</div></div>
                <div className="figure"><div className="label">{t('Dividends in {year}', { year: d.year })}</div><div className="value income"><Money value={d.totals.dividends_ytd} currency={c} /></div></div>
              </div>
            </div>
          </section>

          {hasPositions && (
            <div className="grid-2">
              <Allocation title={t('By asset class')} items={d.allocation.by_class.map((x, i) => ({ ...x, name: t(CLASSES[x.key] ?? CLASSES.other), color: DATA_COLORS[i % DATA_COLORS.length] }))} currency={c} />
              <Allocation title={t('By currency')} items={d.allocation.by_currency.map((x, i) => ({ ...x, name: x.key, color: DATA_COLORS[i % DATA_COLORS.length] }))} currency={c} />
            </div>
          )}

          {accounts.map((a) => (
            <AccountCard key={a.id} a={a} onPrice={setPricing} onSecurity={setSecurity}
              onHolding={(h) => setHolding({ account_id: a.id, ...h })} onChanged={bump} />
          ))}

          <div className="grid-2">
            <Dividends d={d} accounts={accounts} />
            <RecentActivity version={version} onChanged={bump} />
          </div>
          <Imports version={version} onChanged={bump} />
        </>}
      </div>
      {importing && <ImportDialog accounts={accounts} onClose={() => setImporting(false)} onDone={bump} />}
      {activity && <ActivityDialog accounts={accounts} onClose={() => setActivity(null)} onSaved={bump} />}
      {holding && <HoldingDialog h={holding} accounts={accounts} onClose={() => setHolding(null)} onSaved={bump} />}
      {pricing && <PriceDialog p={pricing} onClose={() => setPricing(null)} onSaved={bump} />}
      {security && <SecurityDialog s={security} onClose={() => setSecurity(null)} onSaved={bump} />}
    </>
  )
}

function Allocation({ title, items, currency }) {
  return (
    <section className="card chart-card">
      <div className="card-head"><h2>{title}</h2></div>
      {!items.length ? <Empty title={t('Nothing to show yet')} /> : (
        <div className="alloc">
          <div className="alloc-chart">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={items} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="88%" paddingAngle={2} stroke="var(--sheet)" strokeWidth={2} isAnimationActive={false}>
                  {items.map((x) => <Cell key={x.key} fill={x.color} />)}
                </Pie>
                <Tooltip formatter={(v) => money(v, currency)} contentStyle={{ background: 'var(--sheet)', border: '1px solid var(--rule)', borderRadius: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="alloc-legend">
            {items.map((x) => (
              <div key={x.key} className="alloc-item">
                <i className="dot" style={{ '--dot': x.color }} />
                <span className="grow">{x.name}</span>
                <Money value={x.value} currency={currency} className="small" />
                <span className="small muted num alloc-pct">{x.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function AccountCard({ a, onPrice, onSecurity, onHolding, onChanged }) {
  const toast = useToast()
  const [showAcb, setShowAcb] = useState(false)
  const setReg = async (e) => {
    try { await api.put(`/invest/accounts/${a.id}/registration`, { registration: e.target.value }); onChanged() } catch (err) { toast(err.message, 'error') }
  }
  const cur = a.currency
  return (
    <section className="card">
      <div className="card-head invest-head">
        <div className="grow" style={{ minWidth: 0 }}>
          <h2>{a.name}</h2>
          <div className="sub">{[a.institution, cur].filter(Boolean).join(' · ')}</div>
        </div>
        <select className="input invest-reg" value={a.registration} onChange={setReg} aria-label={t('Account type for tax')} title={a.registration_explicit ? '' : t('Guessed from the account name. Pick the right one.')}>
          {Object.entries(REGISTRATIONS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
        </select>
        <div className="invest-head-total">
          <strong><Money value={a.total} currency={cur} /></strong>
          {a.gain !== null && a.gain_pct !== null && <div className="small"><Money value={a.gain} currency={cur} sign colored /> <span className="muted">{pct(a.gain_pct)}</span></div>}
        </div>
      </div>
      {!a.positions.length ? (
        <div className="list-row muted small">
          <span className="grow">{t('No holdings yet. Import a holdings export, add activity, or add a position by hand.')}</span>
          <button className="btn sm" onClick={() => onHolding({})}><Plus />{t('Add position')}</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table invest-table">
            <thead><tr>
              <th>{t('Security')}</th><th className="amount">{t('Quantity')}</th><th className="amount">{t('Average cost')}</th>
              <th className="amount">{t('Price')}</th><th className="amount">{t('Market value')}</th><th className="amount">{t('Book cost')}</th>
              <th className="amount">{t('Gain or loss')}</th><th />
            </tr></thead>
            <tbody>
              {a.positions.map((p) => (
                <tr key={p.security_id}>
                  <td className="desc">
                    <div><button className="link-btn" onClick={() => onSecurity(p)}>{p.symbol}</button>{p.exchange && <span className="muted small"> · {p.exchange}</span>}</div>
                    <small>{p.name || t(CLASSES[p.asset_class] ?? CLASSES.other)}</small>
                  </td>
                  <td className="amount num">{Number(p.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="amount"><Money value={p.avg_cost} currency={cur} /></td>
                  <td className="amount">
                    <button className="price-btn" onClick={() => onPrice(p)} title={p.fetch_error ? `${t('Last fetch failed')}: ${p.fetch_error}` : t('Update price')}>
                      {p.price === null ? <span className="pill amber">{t('Add price')}</span> : <Money value={p.price} currency={p.currency} />}
                    </button>
                    <div className={`price-age ${p.price_age_days > 7 || p.price === null ? 'stale' : ''}`}>
                      <Clock size={11} /> {p.price_date ? `${ageLabel(p.price_age_days)}` : t('counted at cost')}{p.fetch_error ? ' · ' + t('fetch failed') : ''}
                    </div>
                  </td>
                  <td className="amount">{p.market_value === null ? <span className="pill amber" title={t('No exchange rate')}>{t('no rate')}</span> : <Money value={p.market_value} currency={cur} />}
                    {p.currency !== cur && p.market_value_native !== null && <div className="small muted"><Money value={p.market_value_native} currency={p.currency} /></div>}</td>
                  <td className="amount"><Money value={p.cost} currency={cur} />{p.cost_incomplete && <div className="small muted" title={t('Some activity is in a currency with no exchange rate.')}>{t('incomplete')}</div>}</td>
                  <td className="amount">{p.gain === null ? '—' : <><Money value={p.gain} currency={cur} sign colored /><div className={`small ${p.gain >= 0 ? 'income' : 'expense'}`}>{pct(p.gain_pct)}</div></>}</td>
                  <td className="row-actions">
                    <button className="icon-btn" onClick={() => onHolding({ security_id: p.security_id, symbol: p.symbol, quantity: p.quantity, cost_basis: p.cost })} aria-label={t('Edit position')} title={t('Set position')}><Pencil /></button>
                  </td>
                </tr>
              ))}
              <tr className="cash-row">
                <td className="desc"><div>{t('Cash')}</div><small>{t('From this account’s transactions')}</small></td>
                <td /><td /><td />
                <td className="amount"><Money value={a.cash} currency={cur} /></td>
                <td /><td /><td />
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <div className="list-row invest-foot small">
        <span className="grow muted">{t('Dividends this year')}: <Money value={a.dividends_ytd} currency={a.currency} /></span>
        {a.positions.length > 0 && <button className="btn sm ghost" onClick={() => onHolding({})}><Plus />{t('Add position')}</button>}
        {a.registration === 'non_registered' && a.positions.length > 0 && (
          <button className="btn sm" onClick={() => setShowAcb((v) => !v)}><Calculator />{showAcb ? t('Hide ACB') : t('Adjusted cost base (ACB)')}</button>
        )}
      </div>
      {showAcb && <Acb accountId={a.id} />}
    </section>
  )
}

function Acb({ accountId }) {
  const r = useData(() => api.get(`/invest/acb/${accountId}`), [accountId])
  const [open, setOpen] = useState(null)
  if (!r.data) return <div className="card-body"><Loading rows={2} /></div>
  const d = r.data
  return (
    <div className="acb">
      <div className="banner info acb-note"><Calculator /><div className="banner-body">{t("FinVault's ACB is a helper, not tax advice. It uses the average-cost method in Canadian dollars for this account only and doesn't apply the superficial-loss rule. Check it against your T5008 slips and with an accountant.")}</div></div>
      <Warnings items={d.warnings} />
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>{t('Security')}</th><th className="amount">{t('Units')}</th><th className="amount">{t('ACB')}</th><th className="amount">{t('ACB per unit')}</th><th className="amount">{t('Realized gain in {year}', { year: d.items[0]?.year ?? '' })}</th><th /></tr></thead>
          <tbody>
            {d.items.map((i) => (<Fragment key={i.security_id}>
              <tr>
                <td className="desc"><div>{i.symbol}</div><small>{i.from_snapshot ? t('starts from the position on {date}', { date: date(i.from_snapshot) }) : i.name}</small></td>
                <td className="amount num">{Number(i.units).toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                <td className="amount"><Money value={i.acb} currency="CAD" />{i.incomplete && <div className="small muted">{t('incomplete')}</div>}</td>
                <td className="amount">{i.acb_per_unit === null ? '—' : money(i.acb_per_unit, 'CAD')}</td>
                <td className="amount"><Money value={i.realized_gain_year} currency="CAD" sign colored /></td>
                <td><button className="link-btn small" onClick={() => setOpen(open === i.security_id ? null : i.security_id)}>{open === i.security_id ? t('Hide') : t('Details')}</button></td>
              </tr>
              {open === i.security_id && (
                <tr key={`${i.security_id}-l`} className="acb-ledger"><td colSpan={6}>
                  <table className="table">
                    <thead><tr><th>{t('Date')}</th><th>{t('Activity')}</th><th className="amount">{t('Units')}</th><th className="amount">{t('Amount')}</th><th className="amount">{t('Gain')}</th><th className="amount">{t('ACB after')}</th></tr></thead>
                    <tbody>{i.ledger.map((l, n) => (
                      <tr key={n}><td>{date(l.date)}</td><td>{l.kind === 'opening' ? t('Starting position') : t(KINDS[l.kind] ?? l.kind)}</td>
                        <td className="amount num">{l.quantity}</td><td className="amount">{l.amount === null ? '—' : money(l.amount, 'CAD')}</td>
                        <td className="amount">{l.gain === null ? '' : <Money value={l.gain} currency="CAD" sign colored />}</td>
                        <td className="amount">{money(l.acb_after, 'CAD')}</td></tr>
                    ))}</tbody>
                  </table>
                </td></tr>
              )}
            </Fragment>))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Dividends({ d, accounts }) {
  const names = Object.fromEntries(accounts.map((a) => [a.id, a.name]))
  return (
    <section className="card">
      <div className="card-head"><h2>{t('Dividends in {year}', { year: d.year })}</h2><strong className="income"><Money value={d.dividends.total} currency={d.base_currency} /></strong></div>
      {!d.dividends.items.length ? <div className="list-row muted small">{t('No dividends or distributions recorded this year.')}</div> : (
        <div className="list">
          {d.dividends.items.map((x, i) => (
            <div key={i} className="list-row">
              <div className="grow"><div className="title">{x.symbol ?? '—'} <span className="muted small">· {t(KINDS[x.kind])}</span></div><div className="meta">{date(x.date)} · {names[x.account_id]}</div></div>
              <Money value={x.amount} currency={x.currency} className="strong" />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function RecentActivity({ version, onChanged }) {
  const r = useData(() => api.get('/invest/activities?limit=30'), [version])
  const [confirm, setConfirm] = useState(null)
  const items = r.data ?? []
  return (
    <section className="card">
      <div className="card-head"><h2>{t('Recent activity')}</h2></div>
      {!items.length ? <div className="list-row muted small">{t('No activity yet. Import an activity export or add one by hand.')}</div> : (
        <div className="list invest-activity">
          {items.map((a) => (
            <div key={a.id} className="list-row">
              <div className="grow">
                <div className="title">{t(KINDS[a.kind] ?? a.kind)}{a.symbol ? ` · ${a.symbol}` : ''}</div>
                <div className="meta">{date(a.date)}{a.quantity ? ` · ${t('{n} units', { n: Number(a.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 }) })}` : ''}{a.kind === 'split' ? ` · ${t('ratio {r}', { r: a.split_ratio })}` : ''}</div>
              </div>
              {a.kind !== 'split' && <Money value={a.amount} currency={a.currency} className="strong" />}
              <div className="actions">
                <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete this activity?'), body: t('Positions and ACB are worked out again without it.'), onConfirm: async () => { await api.del(`/invest/activities/${a.id}`); onChanged() } })}><Trash2 /></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </section>
  )
}

function Imports({ version, onChanged }) {
  const r = useData(() => api.get('/invest/imports'), [version])
  const [confirm, setConfirm] = useState(null)
  if (!r.data?.length) return null
  return (
    <section className="card">
      <div className="card-head"><h2>{t('Imported files')}</h2></div>
      <div className="list">
        {r.data.slice(0, 8).map((b) => (
          <div key={b.id} className="list-row">
            <Upload className="row-icon" aria-hidden="true" />
            <div className="grow"><div className="title">{b.filename}</div>
              <div className="meta">{b.account_name} · {t(SOURCES[b.source] ?? b.source)} · {t('{n} added', { n: b.imported })}{b.skipped ? ` · ${t('{n} skipped', { n: b.skipped })}` : ''} · {date(b.created_at)}</div></div>
            <button className="btn sm ghost" onClick={() => setConfirm({ title: t('Undo this import?'), body: t('Removes the activity and positions that came from this file. Prices are kept.'), action: t('Undo import'), onConfirm: async () => { await api.del(`/invest/imports/${b.id}`); onChanged() } })}><Undo2 />{t('Undo')}</button>
          </div>
        ))}
      </div>
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </section>
  )
}

// ---- Dialogs ----------------------------------------------------------------------

function ImportDialog({ accounts, onClose, onDone }) {
  const toast = useToast()
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '')
  const [file, setFile] = useState(null)
  const [source, setSource] = useState('auto')
  const [label, setLabel] = useState('')
  const [asOf, setAsOf] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)

  const form = (opts) => {
    const f = new FormData()
    f.append('account_id', accountId)
    f.append('options', JSON.stringify(opts))
    f.append('file', file)
    return f
  }
  const opts = (over = {}) => ({ source: source === 'auto' ? null : source, account_label: label || null, as_of: asOf || null, ...over })
  const run = async (over) => {
    if (!file) return
    setBusy(true)
    try {
      const p = await api.upload('/invest/import/preview', form(opts(over)))
      setPreview(p)
      if (!asOf && p.as_of) setAsOf(p.as_of)
    } catch (e) { toast(e.message, 'error'); setPreview(null) } finally { setBusy(false) }
  }
  const commit = async () => {
    setBusy(true)
    try {
      const r = await api.upload('/invest/import/commit', form(opts()))
      toast(r.kind === 'holdings' ? t('Imported {n} positions', { n: r.imported }) : t('Imported {n} activities, skipped {s}', { n: r.imported, s: r.skipped }))
      onDone(); onClose()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const needsLabel = preview?.kind === 'holdings' && preview.account_labels.length > 1 && !label
  return (
    <Dialog wide title={t('Import holdings or activity')} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className="btn primary" disabled={!preview || busy || needsLabel || !preview.total} onClick={commit}>{t('Import')}</button>
    </>}>
      <p className="muted small" style={{ marginBottom: 14 }}>{t('Download a CSV from your broker: in Wealthsimple, Activity or Holdings → Export; in Questrade, Reports → Account activity (save the Excel file as CSV). Only the file is read; FinVault never signs in to your broker.')}</p>
      <div className="form-grid">
        <Field label={t('Account')}><select className="input" value={accountId} onChange={(e) => { setAccountId(e.target.value); setPreview(null) }}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label={t('File layout')}><select className="input" value={source} onChange={(e) => { setSource(e.target.value); setPreview(null) }}>
          {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></Field>
        <Field label={t('CSV file')} className="full"><input className="input" type="file" accept=".csv,.txt,.tsv" onChange={(e) => { setFile(e.target.files[0]); setPreview(null) }} /></Field>
      </div>
      <div className="row" style={{ marginTop: 12 }}><button className="btn" disabled={!file || busy} onClick={() => run()}>{t('Preview')}</button></div>
      {preview && (
        <div className="stack" style={{ marginTop: 16, gap: 12 }}>
          <div className="stat-strip">
            <div><small>{t('Layout')}</small><strong className="small">{t(SOURCES[preview.source] ?? preview.source)}</strong></div>
            {preview.kind === 'activity' ? <>
              <div><small>{t('New')}</small><strong>{preview.new}</strong></div>
              <div><small>{t('Already imported')}</small><strong>{preview.duplicates}</strong></div>
            </> : <div><small>{t('Positions')}</small><strong>{preview.total}</strong></div>}
            <div><small>{t('Skipped rows')}</small><strong>{preview.skipped}</strong></div>
          </div>
          {preview.kind === 'holdings' && (
            <div className="form-grid">
              {preview.account_labels.length > 1 && (
                <Field label={t('Which account in the file?')} hint={t('This file lists several accounts.')}>
                  <select className="input" value={label} onChange={(e) => { setLabel(e.target.value); run({ account_label: e.target.value || null }) }}>
                    <option value="">{t('Choose…')}</option>
                    {preview.account_labels.map((l) => <option key={l}>{l}</option>)}
                  </select></Field>
              )}
              <Field label={t('Positions as of')} hint={t('Activity after this date is added on top.')}><input className="input" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
            </div>
          )}
          {Object.keys(preview.skipped_types).length > 0 && <p className="small muted">{t('Cash movements stay with the account’s transactions and were skipped here: {types}.', { types: Object.entries(preview.skipped_types).map(([k, n]) => `${k} (${n})`).join(', ') })}</p>}
          {preview.warnings.length > 0 && <div className="banner warn"><AlertTriangle /><div className="banner-body small">{preview.warnings.slice(0, 5).join(' ')}</div></div>}
          <div className="table-wrap card" style={{ boxShadow: 'none', maxHeight: 280, overflowY: 'auto' }}>
            {preview.kind === 'activity' ? (
              <table className="table">
                <thead><tr><th>{t('Date')}</th><th>{t('Activity')}</th><th>{t('Security')}</th><th className="amount">{t('Quantity')}</th><th className="amount">{t('Amount')}</th></tr></thead>
                <tbody>{preview.activities.map((r, i) => (
                  <tr key={i} className={r.duplicate ? 'dup' : ''}><td>{date(r.date)}</td><td>{t(KINDS[r.kind])}</td><td>{r.symbol}</td>
                    <td className="amount num">{r.quantity || ''}</td><td className="amount">{money(r.amount, r.currency)}</td></tr>
                ))}</tbody>
              </table>
            ) : (
              <table className="table">
                <thead><tr><th>{t('Security')}</th><th className="amount">{t('Quantity')}</th><th className="amount">{t('Book cost')}</th><th className="amount">{t('Price')}</th></tr></thead>
                <tbody>{preview.holdings.map((h, i) => (
                  <tr key={i}><td className="desc"><div>{h.symbol}</div><small>{h.name}{h.account_label ? ` · ${h.account_label}` : ''}</small></td>
                    <td className="amount num">{h.quantity}</td><td className="amount">{money(h.cost_basis, h.cost_currency)}</td>
                    <td className="amount">{h.price === null ? '—' : money(h.price, h.price_currency || 'CAD')}</td></tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </Dialog>
  )
}

function ActivityDialog({ accounts, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ account_id: accounts[0]?.id, date: todayISO(), kind: 'buy', symbol: '', exchange: 'TSX', quantity: '', price: '', amount: '', commission: '', split_ratio: '', currency: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const num = (v) => (v === '' ? null : Number(v))
  const acct = accounts.find((a) => String(a.id) === String(f.account_id))
  const save = async () => {
    try {
      await api.post('/invest/activities', {
        account_id: Number(f.account_id), date: f.date, kind: f.kind, symbol: f.symbol || null, exchange: f.exchange,
        quantity: num(f.quantity) ?? 0, price: num(f.price), amount: num(f.amount), commission: num(f.commission) ?? 0,
        split_ratio: num(f.split_ratio), currency: f.currency || null,
      })
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  const trade = ['buy', 'sell', 'reinvested_dividend'].includes(f.kind)
  return (
    <Dialog title={t('Add activity')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Account')}><select className="input" value={f.account_id} onChange={set('account_id')}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label={t('Activity')}><select className="input" value={f.kind} onChange={set('kind')}>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></Field>
        <Field label={t('Symbol')} hint={f.kind === 'fee' ? t('Optional for account fees') : null}><input className="input" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} placeholder="XEQT" /></Field>
        <Field label={t('Exchange')}><select className="input" value={f.exchange} onChange={set('exchange')}>{['TSX', 'TSXV', 'NEO', 'CSE', 'NYSE', 'NASDAQ', 'ARCA', ''].map((x) => <option key={x} value={x}>{x || t('Other')}</option>)}</select></Field>
        <Field label={t('Date')}><input className="input" type="date" value={f.date} onChange={set('date')} /></Field>
        {f.kind === 'split'
          ? <Field label={t('New units per old unit')} hint={t('2 for a 2-for-1 split, 0.5 for a 1-for-2 consolidation')}><input className="input" type="number" step="any" min="0" value={f.split_ratio} onChange={set('split_ratio')} /></Field>
          : <>
            {trade && <Field label={t('Quantity')}><input className="input" type="number" step="any" min="0" value={f.quantity} onChange={set('quantity')} /></Field>}
            {trade && <Field label={t('Price per unit')}><input className="input" type="number" step="any" min="0" value={f.price} onChange={set('price')} /></Field>}
            <Field label={t('Amount')} hint={trade ? t('Leave empty to use quantity × price') : null}><input className="input" type="number" step="0.01" min="0" value={f.amount} onChange={set('amount')} /></Field>
            {(f.kind === 'buy' || f.kind === 'sell') && <Field label={t('Commission')}><input className="input" type="number" step="0.01" min="0" value={f.commission} onChange={set('commission')} /></Field>}
            <Field label={t('Currency')}><select className="input" value={f.currency || acct?.currency} onChange={set('currency')}>{CURRENCIES.map((x) => <option key={x}>{x}</option>)}</select></Field>
          </>}
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>{t('Activity changes positions and ACB only. The cash side comes from the account’s imported transactions.')}</p>
    </Dialog>
  )
}

function HoldingDialog({ h, accounts, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ account_id: h.account_id, symbol: h.symbol ?? '', exchange: 'TSX', quantity: h.quantity ?? '', cost_basis: h.cost_basis ?? '', price: '', as_of: todayISO() })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const acct = accounts.find((a) => a.id === h.account_id)
  const save = async () => {
    try {
      await api.put('/invest/holdings', { account_id: h.account_id, security_id: h.security_id ?? null, symbol: f.symbol || null, exchange: f.exchange,
        quantity: Number(f.quantity) || 0, cost_basis: Number(f.cost_basis) || 0, price: f.price === '' ? null : Number(f.price), as_of: f.as_of })
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={h.security_id ? t('Set position for {symbol}', { symbol: h.symbol }) : t('Add position')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!f.symbol || f.quantity === ''}>{t('Save')}</button></>}>
      <div className="form-grid">
        {!h.security_id && <>
          <Field label={t('Symbol')}><input className="input" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} placeholder="XEQT" /></Field>
          <Field label={t('Exchange')}><select className="input" value={f.exchange} onChange={set('exchange')}>{['TSX', 'TSXV', 'NEO', 'CSE', 'NYSE', 'NASDAQ', 'ARCA', ''].map((x) => <option key={x} value={x}>{x || t('Other')}</option>)}</select></Field>
        </>}
        <Field label={t('Quantity')}><input className="input" type="number" step="any" min="0" value={f.quantity} onChange={set('quantity')} /></Field>
        <Field label={t('Book cost ({currency})', { currency: acct?.currency ?? '' })} hint={t('Total paid, including commissions')}><input className="input" type="number" step="0.01" min="0" value={f.cost_basis} onChange={set('cost_basis')} /></Field>
        <Field label={t('As of')}><input className="input" type="date" value={f.as_of} onChange={set('as_of')} /></Field>
        <Field label={t('Price today')} hint={t('Optional')}><input className="input" type="number" step="any" min="0" value={f.price} onChange={set('price')} /></Field>
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>{t('This replaces the position on that date. Activity dated after it is added on top.')}</p>
    </Dialog>
  )
}

function PriceDialog({ p, onClose, onSaved }) {
  const toast = useToast()
  const hist = useData(() => api.get(`/invest/securities/${p.security_id}/prices`), [p.security_id])
  const [close, setClose] = useState(p.price ?? '')
  const [on, setOn] = useState(todayISO())
  const save = async () => {
    try { await api.post(`/invest/securities/${p.security_id}/prices`, { close: Number(close), date: on }); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={t('Price of {symbol}', { symbol: p.symbol })} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={!close} onClick={save}>{t('Save price')}</button></>}>
      {p.fetch_error && <div className="banner warn" style={{ marginBottom: 12 }}><AlertTriangle /><div className="banner-body small">{t('The last automatic fetch failed, so the last price is kept.')} {p.fetch_error}</div></div>}
      <div className="form-grid">
        <Field label={t('Closing price ({currency})', { currency: p.currency })}><input className="input" type="number" step="any" min="0" value={close} onChange={(e) => setClose(e.target.value)} /></Field>
        <Field label={t('Date')}><input className="input" type="date" value={on} onChange={(e) => setOn(e.target.value)} /></Field>
      </div>
      {hist.data?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="small strong" style={{ marginBottom: 6 }}>{t('History')}</div>
          <div className="list card" style={{ boxShadow: 'none', maxHeight: 200, overflowY: 'auto' }}>
            {hist.data.map((h) => (
              <div key={h.id} className="list-row" style={{ padding: '7px 14px' }}>
                <span className="grow small">{date(h.date)} <span className="muted">· {t({ manual: 'typed', import: 'from import', stooq: 'Stooq' }[h.source] ?? h.source)}</span></span>
                <span className="small money-v">{money(h.close, p.currency)}</span>
                <button className="icon-btn" aria-label={t('Delete')} onClick={async () => { await api.del(`/invest/prices/${h.id}`); hist.reload(); onSaved() }}><Trash2 /></button>
              </div>
            ))}
          </div>
        </div>
      )}
    </Dialog>
  )
}

function SecurityDialog({ s, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ name: s.name ?? '', exchange: s.exchange ?? '', currency: s.currency, asset_class: s.asset_class })
  const [ps, setPs] = useState(undefined) // price lookup symbol; undefined until edited
  const all = useData(() => api.get('/invest/securities'), [])
  const full = all.data?.find((x) => x.id === s.security_id)
  const priceSymbol = ps ?? full?.price_symbol ?? ''
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    try {
      await api.patch(`/invest/securities/${s.security_id}`, { ...f, price_symbol: priceSymbol || null })
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={s.symbol} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Name')} className="full"><input className="input" value={f.name} onChange={set('name')} /></Field>
        <Field label={t('Asset class')}><select className="input" value={f.asset_class} onChange={set('asset_class')}>{Object.entries(CLASSES).map(([k, l]) => <option key={k} value={k}>{t(l)}</option>)}</select></Field>
        <Field label={t('Trades in')}><select className="input" value={f.currency} onChange={set('currency')}>{CURRENCIES.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label={t('Exchange')}><input className="input" value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value.toUpperCase() })} /></Field>
        <Field label={t('Price lookup symbol')} hint={t('Only if automatic prices use the wrong ticker, e.g. xeqt.ca')}><input className="input" value={priceSymbol} onChange={(e) => setPs(e.target.value)} /></Field>
      </div>
      <p className="small muted" style={{ marginTop: 12 }}><Tag size={12} /> {t('When automatic prices are on, only the ticker symbol is sent to the price service.')}</p>
    </Dialog>
  )
}
