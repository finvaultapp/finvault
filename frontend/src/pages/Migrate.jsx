// Move from another app: a one-time wizard that brings a household's history in from YNAB, Actual Budget,
// Mint, Monarch Money or another app's CSV. The files stay in the browser and go with each step.
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ArrowRight, ChevronDown, ChevronRight, FileUp, Loader2, RotateCcw, Truck, X } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Confirm, Field, Loading, PageHead, Switch, activateOnKey, useAnnounce, useData, useToast } from '../components/ui'
import Postmark from '../components/Postmark'
import { ACCOUNT_TYPES, CURRENCIES, date } from '../lib/format'
import { t } from '../i18n'
import { serverText } from '../lib/serverText'

const SEP = '\u001f'
const SOURCES = [
  { id: '', get label() { return t('Detect automatically') } },
  { id: 'ynab', label: 'YNAB', get help() { return t('In YNAB, open the budget menu and choose Export budget. Upload the zip as it is: it holds Register.csv and Budget.csv.') } },
  { id: 'actual', label: 'Actual Budget', get help() { return t('In Actual Budget, open All accounts, select the transactions and choose Export. Upload the CSV. A full budget backup (a zip with db.sqlite) cannot be read.') } },
  { id: 'mint', label: 'Mint', get help() { return t('Use the transactions.csv you downloaded from Mint before it closed. Labels become tags.') } },
  { id: 'monarch', label: 'Monarch Money', get help() { return t('In Monarch, open Transactions and choose Download CSV. Tags come across as tags.') } },
  { id: 'generic', get label() { return t('Other app') }, get help() { return t('Any CSV with a date and an amount. Each file becomes one account named after the file; you can match its columns after uploading.') } },
]
const ROLES = {
  get date() { return t('Date') }, get description() { return t('Description') }, get amount() { return t('Amount (signed)') },
  get debit() { return t('Money out') }, get credit() { return t('Money in') }, get category() { return t('Category') },
  get type() { return t('Debit/credit type') }, get description2() { return t('Extra description') },
}
const DATE_FORMATS = [['%m/%d/%Y', 'MM/DD/YYYY'], ['%d/%m/%Y', 'DD/MM/YYYY'], ['%Y-%m-%d', 'YYYY-MM-DD'], ['%m/%d/%y', 'MM/DD/YY'], ['%d/%m/%y', 'DD/MM/YY']]
const KINDS = { get expense() { return t('Spending') }, get income() { return t('Income') }, get transfer() { return t('Transfer') } }

export default function Migrate() {
  const { version, bump } = useApp()
  const toast = useToast()
  const accounts = useData(() => api.get('/accounts'), [version])
  const categories = useData(() => api.get('/categories'), [version])
  const [step, setStep] = useState(1)
  const [files, setFiles] = useState([])
  const [source, setSource] = useState('')
  const [dateFormat, setDateFormat] = useState('')
  const [generic, setGeneric] = useState({})
  const [analysis, setAnalysis] = useState(null)
  const [plan, setPlan] = useState({ accounts: {}, categories: {}, include_uncleared: true, create_budgets: false })
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState(null)
  const [undone, setUndone] = useState({})
  const stepRef = useRef(null)
  const firstStep = useRef(true)
  const announce = useAnnounce()
  // Each step replaces the last one: move focus to its heading so keyboard and screen-reader users land on it.
  useEffect(() => {
    if (firstStep.current) { firstStep.current = false; return }
    const h = stepRef.current?.querySelector('h2')
    if (h) { h.tabIndex = -1; h.focus() }
  }, [step])

  const form = (extra = {}) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    fd.append('options', JSON.stringify({ source: source || null, date_format: dateFormat || null, generic, ...extra }))
    return fd
  }

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn() } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const analyze = () => run(async () => {
    const a = await api.upload('/migrate/analyze', form())
    setAnalysis(a)
    // Keep choices already made for accounts and categories that are still there.
    setPlan((p) => ({
      ...p,
      create_budgets: p.create_budgets || !!a.budgets.month,
      accounts: Object.fromEntries(a.accounts.map((x) => [x.source, p.accounts[x.source] ?? x.suggestion])),
      categories: Object.fromEntries(a.categories.map((x) => [x.key, p.categories[x.key] ?? x.suggestion])),
    }))
    if (!source) setSource(a.source)
    announce(a.total === 1 ? t('Read {n} transaction', { n: a.total }) : t('Read {n} transactions', { n: a.total }))
  })

  const runPreview = () => run(async () => { setPreview(await api.upload('/migrate/preview', form({ plan }))); setStep(4) })

  const commit = () => run(async () => {
    const r = await api.upload('/migrate/commit', form({ plan }))
    setResult(r); setStep(5); bump()
    toast(t('Moved {n} transactions into FinVault', { n: r.imported }))
  })

  const undo = async (batchIds) => {
    let removed = 0
    for (const id of batchIds) {
      const r = await api.del(`/imports/batches/${id}`)
      removed += r.removed
      setUndone((u) => ({ ...u, [id]: true }))
    }
    toast(t('Removed {n} transactions', { n: removed })); bump()
  }

  const reset = () => { setStep(1); setFiles([]); setAnalysis(null); setPreview(null); setResult(null); setGeneric({}); setSource(''); setDateFormat(''); setUndone({}); setPlan({ accounts: {}, categories: {}, include_uncleared: true, create_budgets: false }) }

  if (!accounts.data || !categories.data) return <Loading />
  const labels = [t('Upload'), t('Accounts'), t('Categories'), t('Preview'), t('Done')]
  const chosen = Object.values(plan.accounts).filter((c) => c.action !== 'skip').length

  return (
    <>
      <PageHead title={t('Move from another app')} sub={t('Bring your history in once from YNAB, Actual Budget, Mint, Monarch Money or another app. For your monthly bank files, use Import a statement.')}>
        <Link to="/import" className="btn"><ArrowLeft size={16} />{t('Import a statement')}</Link>
      </PageHead>

      <ol className="steps move-steps" aria-label={t('Steps')}>
        {labels.map((l, i) => (
          <li key={l} className="row" style={{ gap: 8 }}>
            {i > 0 && <span className="step-sep" aria-hidden="true" />}
            <span className={`step ${step === i + 1 ? 'on' : step > i + 1 ? 'done' : ''}`} aria-current={step === i + 1 ? 'step' : undefined}><b>{i + 1}</b>{l}{step > i + 1 && <span className="sr"> ({t('done')})</span>}</span>
          </li>
        ))}
      </ol>

      {error && <div className="banner warn" role="alert" style={{ marginBottom: 16 }}><AlertTriangle /><div className="banner-body">{error}</div></div>}

      <div ref={stepRef}>
      {step === 1 && (
        <UploadStep files={files} setFiles={(f) => { setFiles(f); setAnalysis(null) }} source={source} setSource={setSource}
          dateFormat={dateFormat} setDateFormat={setDateFormat} analysis={analysis} generic={generic} setGeneric={setGeneric}
          busy={busy} analyze={analyze} next={() => setStep(2)} />
      )}
      {step === 2 && analysis && (
        <AccountsStep analysis={analysis} plan={plan} setPlan={setPlan} existing={(accounts.data.items ?? []).filter((a) => !a.is_archived)}
          back={() => setStep(1)} next={() => setStep(3)} chosen={chosen} />
      )}
      {step === 3 && analysis && (
        <CategoriesStep analysis={analysis} plan={plan} setPlan={setPlan} existing={categories.data} busy={busy}
          back={() => setStep(2)} next={runPreview} />
      )}
      {step === 4 && preview && (
        <PreviewStep preview={preview} analysis={analysis} plan={plan} busy={busy} back={() => setStep(3)} commit={commit} />
      )}
      {step === 5 && result && (
        <DoneStep result={result} analysis={analysis} undone={undone} reset={reset}
          askUndo={(ids, title, body) => setConfirm({ title, body, action: t('Undo'), onConfirm: () => undo(ids) })} />
      )}
      </div>
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function UploadStep({ files, setFiles, source, setSource, dateFormat, setDateFormat, analysis, generic, setGeneric, busy, analyze, next }) {
  const inputRef = useRef(null)
  const [over, setOver] = useState(false)
  const help = SOURCES.find((s) => s.id === (source || analysis?.source))?.help
  const add = (list) => setFiles([...files, ...Array.from(list)].filter((f, i, all) => all.findIndex((g) => g.name === f.name) === i))
  const setRole = (file, col, role) => {
    const g = analysis.generic.find((x) => x.filename === file)
    const current = generic[file]?.mapping ?? g.mapping
    const mapping = Object.fromEntries(Object.entries(current).filter(([, c]) => c !== col))
    if (role) mapping[role] = col
    setGeneric({ ...generic, [file]: { ...generic[file], mapping } })
  }
  return (
    <div className="grid-2 move-upload">
      <section className="card">
        <div className="card-head"><h2>{t('Your export files')}</h2></div>
        <div className="card-body stack" style={{ gap: 16 }}>
          <Field label={t('Coming from')}>
            <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
              {SOURCES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </Field>
          <div className={`dropzone ${over ? 'over' : ''}`} role="button" tabIndex={0} aria-describedby="move-drop-hint"
            onClick={() => inputRef.current?.click()} onKeyDown={activateOnKey(() => inputRef.current?.click())}
            onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}>
            <FileUp size={28} style={{ marginBottom: 8 }} />
            <div><strong>{t('Drop the export here')}</strong></div>
            <div className="small" id="move-drop-hint">{t('or click to choose · a zip or one or more CSV files')}</div>
            <input ref={inputRef} type="file" hidden multiple accept=".zip,.csv,.tsv,.txt,application/zip,text/csv" onChange={(e) => { add(e.target.files); e.target.value = '' }} />
          </div>
          {files.length > 0 && (
            <ul className="move-files" aria-label={t('Chosen files')}>
              {files.map((f) => (
                <li key={f.name}><FileUp size={15} aria-hidden="true" /><span className="grow">{f.name}</span>
                  <button className="icon-btn" aria-label={t('Remove {file}', { file: f.name })} onClick={() => setFiles(files.filter((g) => g !== f))}><X size={15} /></button></li>
              ))}
            </ul>
          )}
          {analysis?.date_format_ambiguous && (
            <Field label={t('Date format')} hint={t('Dates could be month-first or day-first. Pick the one your app used.')}>
              <select className="input sm" value={dateFormat || analysis.date_format || ''} onChange={(e) => setDateFormat(e.target.value)}>
                {DATE_FORMATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
          )}
          {analysis?.generic?.map((g) => (
            <div key={g.filename} className="move-mapping">
              <p className="strong">{g.filename}</p>
              <p className="small muted" style={{ margin: '2px 0 10px' }}>{t('Tell FinVault what each column holds. You need a date and either an amount or money out / money in.')}</p>
              <div className="mapping-grid">
                {g.columns.map((col, i) => {
                  const mapping = generic[g.filename]?.mapping ?? g.mapping
                  const role = Object.entries(mapping).find(([, c]) => c === i)?.[0] ?? ''
                  return (
                    <Field key={i} label={col || t('Column {n}', { n: i + 1 })} hint={g.sample_rows[0]?.[i] ? t('e.g. {value}', { value: g.sample_rows[0][i].slice(0, 28) }) : t('empty')}>
                      <select className="input sm" value={role} onChange={(e) => setRole(g.filename, i, e.target.value)}>
                        <option value="">{t('Ignore')}</option>
                        {Object.entries(ROLES).map(([r, l]) => <option key={r} value={r}>{l}</option>)}
                      </select>
                    </Field>
                  )
                })}
              </div>
            </div>
          ))}
          {analysis && (
            <div className="stat-strip">
              <div><small>{t('Read as')}</small><strong>{analysis.source_name === 'Other app' ? t('Other app') : analysis.source_name}</strong></div>
              <div><small>{t('Transactions')}</small><strong>{analysis.total}</strong></div>
              <div><small>{t('Accounts')}</small><strong>{analysis.accounts.length}</strong></div>
              <div><small>{t('Categories')}</small><strong>{analysis.categories.length}</strong></div>
            </div>
          )}
          {analysis?.warnings?.map((w) => <div className="banner warn" key={w}><AlertTriangle /><div className="banner-body">{serverText(w)}</div></div>)}
          <div className="row wrap">
            <span className="spacer" />
            <button className="btn" onClick={analyze} disabled={!files.length || busy}>
              {busy ? <Loader2 className="spin" size={16} /> : null}{analysis ? t('Read again') : t('Read the files')}
            </button>
            <button className="btn primary" onClick={next} disabled={!analysis || !analysis.total || busy}>{t('Continue')}<ArrowRight size={16} /></button>
          </div>
        </div>
      </section>
      <section className="card">
        <div className="card-head"><h2>{t('How to export')}</h2></div>
        <div className="card-body stack" style={{ gap: 12 }}>
          {help ? <p>{help}</p> : SOURCES.filter((s) => s.help).map((s) => <p key={s.id}><span className="strong">{s.label}.</span> {s.help}</p>)}
          <p className="small muted">{t('This is a one-time move. Running it again is safe: anything already in FinVault, from an earlier move or a bank statement, is skipped.')}</p>
        </div>
      </section>
    </div>
  )
}

function accountValue(c) { return c.action === 'map' ? `a:${c.account_id}` : c.action }

function AccountsStep({ analysis, plan, setPlan, existing, back, next, chosen }) {
  const set = (src, choice) => setPlan((p) => ({ ...p, accounts: { ...p.accounts, [src]: choice } }))
  const pick = (a, value) => {
    if (value === 'skip') set(a.source, { action: 'skip' })
    else if (value === 'create') set(a.source, a.suggestion.action === 'create' ? a.suggestion : { action: 'create', name: a.source, type: 'checking', currency: 'CAD', country: 'CA', institution: '' })
    else set(a.source, { action: 'map', account_id: Number(value.slice(2)) })
  }
  const anyUncleared = analysis.accounts.some((a) => a.uncleared)
  return (
    <section className="card">
      <div className="card-head"><div><h2>{t('Match your accounts')}</h2><p className="sub">{t('Bring each account into one you already have, or create it. Skipped accounts are left out.')}</p></div></div>
      <div className="list">
        {analysis.accounts.map((a) => {
          const c = plan.accounts[a.source] ?? a.suggestion
          const edit = (patch) => set(a.source, { ...c, ...patch })
          return (
            <div className="move-account" key={a.source}>
              <div className="move-account-head">
                <div className="grow">
                  <div className="title">{a.source}</div>
                  <div className="meta">{a.count === 1 ? t('{n} transaction', { n: a.count }) : t('{n} transactions', { n: a.count })} · {date(a.date_range[0])} – {date(a.date_range[1])}
                    {a.uncleared ? ` · ${t('{n} uncleared', { n: a.uncleared })}` : ''}{a.transfers ? ` · ${t('{n} transfers', { n: a.transfers })}` : ''}</div>
                </div>
                <select className="input sm move-choice" value={accountValue(c)} onChange={(e) => pick(a, e.target.value)} aria-label={t('Where {account} goes', { account: a.source })}>
                  <option value="create">{t('Create a new account')}</option>
                  {existing.length > 0 && <optgroup label={t('Existing accounts')}>{existing.map((x) => <option key={x.id} value={`a:${x.id}`}>{x.name}</option>)}</optgroup>}
                  <option value="skip">{t("Don't bring in")}</option>
                </select>
              </div>
              {c.action === 'create' && (
                <div className="move-account-form">
                  <Field label={t('Name')}><input className="input sm" value={c.name} maxLength={120} onChange={(e) => edit({ name: e.target.value })} /></Field>
                  <Field label={t('Type')}>
                    <select className="input sm" value={c.type} onChange={(e) => edit({ type: e.target.value })}>
                      {Object.entries(ACCOUNT_TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  </Field>
                  <Field label={t('Currency')}>
                    <select className="input sm" value={c.currency} onChange={(e) => edit({ currency: e.target.value, country: e.target.value === 'CAD' ? 'CA' : c.country })}>
                      {[...new Set([c.currency, ...CURRENCIES])].map((x) => <option key={x} value={x}>{x}</option>)}
                    </select>
                  </Field>
                  <Field label={t('Country')} hint={c.country === 'CA' ? t('Canadian accounts are import-only.') : undefined}>
                    <input className="input sm" value={c.country} maxLength={2} onChange={(e) => edit({ country: e.target.value.toUpperCase() })} />
                  </Field>
                  {a.starting_balance != null && <p className="small muted move-full">{t('The starting balance from your old app becomes this account\'s opening balance.')}</p>}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="card-body row wrap move-foot">
        {anyUncleared && (
          <label className="row" style={{ gap: 10 }}>
            <Switch checked={plan.include_uncleared} onChange={(v) => setPlan((p) => ({ ...p, include_uncleared: v }))} label={t('Include uncleared transactions')} />
            <span><span className="strong">{t('Include uncleared transactions')}</span><br /><span className="small muted">{t("They haven't reached the bank yet. A later statement import that has them is matched, not doubled.")}</span></span>
          </label>
        )}
        <span className="spacer" />
        <button className="btn" onClick={back}><ArrowLeft size={16} />{t('Back')}</button>
        <button className="btn primary" onClick={next} disabled={!chosen}>{t('Continue')}<ArrowRight size={16} /></button>
      </div>
    </section>
  )
}

function categoryValue(c) { return c.action === 'map' ? `c:${c.category_id}` : c.action }

function CategoriesStep({ analysis, plan, setPlan, existing, busy, back, next }) {
  const set = (key, choice) => setPlan((p) => ({ ...p, categories: { ...p.categories, [key]: choice } }))
  const byId = useMemo(() => Object.fromEntries(existing.map((c) => [c.id, c])), [existing])
  const label = (c) => (c.parent_id && byId[c.parent_id] ? `${byId[c.parent_id].name} › ${c.name}` : c.name)
  const options = useMemo(() => [...existing].sort((a, b) => label(a).localeCompare(label(b))), [existing]) // eslint-disable-line react-hooks/exhaustive-deps
  const groups = useMemo(() => {
    const out = []
    for (const c of analysis.categories) {
      const g = c.group ?? ''
      let entry = out.find((x) => x.group === g)
      if (!entry) { entry = { group: g, items: [] }; out.push(entry) }
      entry.items.push(c)
    }
    return out
  }, [analysis])
  const pick = (c, value) => {
    if (value === 'skip') set(c.key, { action: 'skip' })
    else if (value === 'create') set(c.key, { action: 'create', name: c.name, kind: c.kind, parent: c.group })
    else set(c.key, { action: 'map', category_id: Number(value.slice(2)) })
  }
  return (
    <section className="card">
      <div className="card-head"><div><h2>{t('Match your categories')}</h2><p className="sub">{t('Groups from your old app become parent categories, with their categories inside. Transfers between accounts you bring in are matched on their own.')}</p></div></div>
      {!analysis.categories.length && <div className="card-body muted">{t('These files have no categories. Rules and remembered merchants will sort what they can.')}</div>}
      {groups.map((g) => (
        <div key={g.group} className="move-group">
          <h3>{g.group || t('Not in a group')}</h3>
          <div className="list">
            {g.items.map((c) => {
              const choice = plan.categories[c.key] ?? c.suggestion
              return (
                <div className="list-row move-cat" key={c.key}>
                  <div className="grow">
                    <div className="title">{c.name}</div>
                    <div className="meta">{c.count === 1 ? t('{n} transaction', { n: c.count }) : t('{n} transactions', { n: c.count })}</div>
                  </div>
                  {choice.action === 'create' && (
                    <select className="input sm move-kind" value={choice.kind} onChange={(e) => set(c.key, { ...choice, kind: e.target.value })} aria-label={t('Kind of {category}', { category: c.name })}>
                      {Object.entries(KINDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  )}
                  <select className="input sm move-choice" value={categoryValue(choice)} onChange={(e) => pick(c, e.target.value)} aria-label={t('Where {category} goes', { category: c.name })}>
                    <option value="create">{c.group ? t('New category under {group}', { group: c.group }) : t('New category')}</option>
                    <optgroup label={t('Existing categories')}>{options.map((x) => <option key={x.id} value={`c:${x.id}`}>{label(x)}</option>)}</optgroup>
                    <option value="skip">{t('Leave uncategorized')}</option>
                  </select>
                </div>
              )
            })}
          </div>
        </div>
      ))}
      <div className="card-body row wrap move-foot">
        {analysis.budgets.month && (
          <label className="row" style={{ gap: 10 }}>
            <Switch checked={plan.create_budgets} onChange={(v) => setPlan((p) => ({ ...p, create_budgets: v }))} label={t('Create monthly budgets')} />
            <span><span className="strong">{t('Create monthly budgets')}</span><br /><span className="small muted">{t('From what you budgeted in {month}: {n} categories. Budgets you already have are kept.', { month: date(analysis.budgets.month, { month: 'long', year: 'numeric' }), n: analysis.budgets.lines })}</span></span>
          </label>
        )}
        <span className="spacer" />
        <button className="btn" onClick={back}><ArrowLeft size={16} />{t('Back')}</button>
        <button className="btn primary" onClick={next} disabled={busy}>{busy ? <Loader2 className="spin" size={16} /> : null}{t('Preview')}<ArrowRight size={16} /></button>
      </div>
    </section>
  )
}

function PreviewStep({ preview, busy, back, commit }) {
  const [open, setOpen] = useState(null)
  return (
    <section className="card">
      <div className="card-head"><div><h2>{t('Check before moving')}</h2><p className="sub">{t('Rows already in FinVault are skipped: the same transaction from an earlier move, or one a bank statement brought in.')}</p></div></div>
      <div className="card-body">
        <div className="stat-strip">
          <div><small>{t('New')}</small><strong className="income">{preview.new}</strong></div>
          <div><small>{t('Already in FinVault')}</small><strong className="muted">{preview.duplicates}</strong></div>
          <div><small>{t('Accounts')}</small><strong>{preview.accounts.length}</strong></div>
        </div>
      </div>
      <div className="table-wrap">
        <table className="table move-table">
          <thead><tr><th scope="col">{t('Account')}</th><th scope="col" className="hide-sm">{t('Dates')}</th><th scope="col" className="amount">{t('New')}</th><th scope="col" className="amount">{t('Already here')}</th><th scope="col" className="amount hide-sm">{t('Probably already here')}</th><th scope="col"><span className="sr">{t('Skipped rows')}</span></th></tr></thead>
          <tbody>
            {preview.accounts.map((a) => (
              <Fragment key={a.source}>
                <tr>
                  <td className="desc"><div>{a.name} {a.create && <span className="pill blue">{t('new account')}</span>}</div>{a.source !== a.name && <small>{t('from {name}', { name: a.source })}</small>}
                    {a.uncleared_skipped > 0 && <small>{t('{n} uncleared left out', { n: a.uncleared_skipped })}</small>}</td>
                  <td className="hide-sm num" style={{ whiteSpace: 'nowrap' }}>{a.date_range ? `${date(a.date_range[0])} – ${date(a.date_range[1])}` : '—'}</td>
                  <td className="amount income">{a.new}</td>
                  <td className="amount muted">{a.exact_duplicates}</td>
                  <td className="amount muted hide-sm">{a.likely_duplicates}</td>
                  <td>{a.duplicates.length > 0 && (
                    <button className="btn sm ghost" aria-expanded={open === a.source} onClick={() => setOpen(open === a.source ? null : a.source)}>
                      {open === a.source ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{t('Show skipped')}<span className="sr"> · {a.name}</span>
                    </button>)}</td>
                </tr>
                {open === a.source && (
                  <tr key={`${a.source}-dups`} className="move-dups"><td colSpan={6}>
                    <table className="table">
                      <caption className="sr">{t('Skipped rows for {account}', { account: a.name })}</caption>
                      <tbody>
                        {a.duplicates.map((d, i) => (
                          <tr key={i}><td className="num">{date(d.date)}</td><td>{d.description}</td><td className="amount">{d.amount.toFixed(2)}</td>
                            <td><span className="pill">{d.kind === 'exact' ? t('already imported') : t('probably already here')}</span></td></tr>
                        ))}
                      </tbody>
                    </table>
                    {a.exact_duplicates + a.likely_duplicates > a.duplicates.length && <p className="small muted">{t('Showing the first {n} of {total}.', { n: a.duplicates.length, total: a.exact_duplicates + a.likely_duplicates })}</p>}
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card-body row wrap move-foot">
        <span className="spacer" />
        <button className="btn" onClick={back}><ArrowLeft size={16} />{t('Back')}</button>
        <button className="btn primary" onClick={commit} disabled={busy || preview.new === 0}>
          {busy ? <Loader2 className="spin" size={16} /> : <Truck size={16} />}
          {preview.new === 0 ? t('Nothing new to bring in') : preview.new === 1 ? t('Move {n} transaction', { n: preview.new }) : t('Move {n} transactions', { n: preview.new })}
        </button>
      </div>
    </section>
  )
}

function DoneStep({ result, analysis, undone, askUndo, reset }) {
  const live = result.accounts.filter((a) => !undone[a.batch_id] && a.imported > 0)
  const extras = [
    result.accounts_created ? (result.accounts_created === 1 ? t('1 account created') : t('{n} accounts created', { n: result.accounts_created })) : null,
    result.categories_created ? (result.categories_created === 1 ? t('1 category created') : t('{n} categories created', { n: result.categories_created })) : null,
    result.transfers_matched ? (result.transfers_matched === 1 ? t('{n} transfer between your accounts matched.', { n: 1 }) : t('{n} transfers between your accounts matched.', { n: result.transfers_matched })) : null,
    result.budgets_created ? t('{n} monthly budgets set', { n: result.budgets_created }) : null,
    result.labelled ? (result.labelled === 1 ? t('tags kept on 1 transaction') : t('tags kept on {n} transactions', { n: result.labelled })) : null,
  ].filter(Boolean)
  return (
    <section className="card">
      <div className="card-body row wrap" style={{ gap: 16 }}>
        <Postmark top={analysis?.source_name ?? t('Moved')} date={new Date().toISOString()} bottom={t('SORTED')} />
        <div className="grow">
          <h2>{result.imported === 1 ? t('Moved {n} transaction', { n: 1 }) : t('Moved {n} transactions', { n: result.imported })}</h2>
          <p className="muted">{result.skipped ? t('{n} already in FinVault were skipped.', { n: result.skipped }) + ' ' : ''}{extras.join(' · ')}</p>
        </div>
        <Link to="/transactions" className="btn">{t('See transactions')}</Link>
        <button className="btn primary" onClick={reset}><FileUp size={16} />{t('Move another file')}</button>
      </div>
      <div className="list">
        {result.accounts.map((a) => (
          <div className="list-row" key={a.batch_id}>
            <FileUp className="row-icon" aria-hidden="true" />
            <div className="grow">
              <div className="title">{a.name}</div>
              <div className="meta">{undone[a.batch_id] ? t('Undone') : `${t('{n} added', { n: a.imported })}${a.skipped ? t(', {n} skipped', { n: a.skipped }) : ''}`}{a.date_range ? ` · ${date(a.date_range[0])} – ${date(a.date_range[1])}` : ''}</div>
            </div>
            {!undone[a.batch_id] && a.imported > 0 && (
              <button className="btn sm ghost" aria-label={t('Undo {account}', { account: a.name })} onClick={() => askUndo([a.batch_id], t('Undo this account?'), t('Removes the {n} transactions this move added to {account}. Edits you made to them are lost.', { n: a.imported, account: a.name }))}>
                <RotateCcw size={14} />{t('Undo')}
              </button>
            )}
          </div>
        ))}
      </div>
      {live.length > 1 && (
        <div className="card-body row move-foot">
          <span className="small muted">{t('Accounts and categories the move created stay; delete them from their pages if you no longer want them.')}</span>
          <span className="spacer" />
          <button className="btn danger" onClick={() => askUndo(live.map((a) => a.batch_id), t('Undo the whole move?'), t('Removes all {n} transactions this move added. Edits you made to them are lost.', { n: live.reduce((s, a) => s + a.imported, 0) }))}>
            <RotateCcw size={16} />{t('Undo the whole move')}
          </button>
        </div>
      )}
    </section>
  )
}
