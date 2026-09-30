import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowRight, CheckCircle2, FileUp, Info, Loader2, RotateCcw, ShieldCheck, Truck, Upload } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Confirm, Empty, Field, Loading, Money, PageHead, Switch, activateOnKey, useData, useToast } from '../components/ui'
import { AccountDialog } from './Accounts'
import Postmark from '../components/Postmark'
import WatchedFolder from '../components/WatchedFolder'
import { date } from '../lib/format'
import { t } from '../i18n'
import { serverText } from '../lib/serverText'

// Getters so labels translate at render time.
const ROLE_LABELS = {
  get date() { return t('Date') }, get description() { return t('Description') }, get description2() { return t('Extra description') },
  get payee() { return t('Payee') }, get amount() { return t('Amount (signed)') },
  get amount_alt() { return t('Amount, 2nd currency') }, get debit() { return t('Money out') }, get credit() { return t('Money in') },
  get currency() { return t('Currency') }, get type() { return t('Debit/credit type') },
  get category() { return t('Bank category') }, get balance() { return t('Balance (ignored)') }, get id() { return t('Reference ID') },
}
const DATE_FORMATS = [
  ['', 'Detect automatically'], ['%m/%d/%Y', 'MM/DD/YYYY'], ['%d/%m/%Y', 'DD/MM/YYYY'], ['%Y-%m-%d', 'YYYY-MM-DD'],
  ['%Y%m%d', 'YYYYMMDD'], ['%m/%d/%y', 'MM/DD/YY'], ['%d/%m/%y', 'DD/MM/YY'], ['%d-%b-%Y', 'DD-Mon-YYYY'],
]

export default function Import() {
  const [params] = useSearchParams()
  const { version, bump } = useApp()
  const toast = useToast()
  const accounts = useData(() => api.get('/accounts'), [version])
  const presets = useData(() => api.get('/imports/presets'), [])
  const batches = useData(() => api.get('/imports/batches'), [version])
  const [accountId, setAccountId] = useState(params.get('account') ?? '')
  const [file, setFile] = useState(null)
  const [options, setOptions] = useState({})
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(null)
  const [adding, setAdding] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [over, setOver] = useState(false)
  const inputRef = useRef(null)
  const doneRef = useRef(null)

  const accts = (accounts.data?.items ?? []).filter((a) => !a.is_archived)
  const account = accts.find((a) => String(a.id) === String(accountId))
  const presetList = presets.data?.presets ?? []
  const preset = presetList.find((p) => p.id === (options.preset || account?.import_preset))

  useEffect(() => { if (!accountId && accts.length === 1) setAccountId(String(accts[0].id)) }, [accts, accountId])
  // The "imported" card replaces the button that was pressed: put focus on its heading.
  useEffect(() => { if (done) doneRef.current?.focus() }, [done])

  const form = (opts) => {
    const fd = new FormData()
    fd.append('account_id', accountId)
    fd.append('options', JSON.stringify(opts))
    fd.append('file', file)
    return fd
  }

  const runPreview = async (opts = options) => {
    if (!file || !accountId) return
    setBusy(true); setError('')
    try { setPreview(await api.upload('/imports/preview', form(opts))) } catch (e) { setError(e.message); setPreview(null) }
    setBusy(false)
  }
  useEffect(() => { if (file) setDone(null); runPreview() }, [file, accountId]) // eslint-disable-line react-hooks/exhaustive-deps

  const change = (patch) => { const next = { ...options, ...patch }; setOptions(next); runPreview(next) }
  const setRole = (col, role) => {
    const mapping = Object.fromEntries(Object.entries(preview.mapping).filter(([, c]) => c !== col))
    if (role) mapping[role] = col
    change({ mapping })
  }

  const commit = async () => {
    setBusy(true)
    try {
      const r = await api.upload('/imports/commit', form(options))
      setDone(r); setPreview(null); setFile(null); setOptions({})
      toast(t('Imported {n} transactions', { n: r.imported }))
      bump()
    } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }

  if (!accounts.data || !presets.data) return <Loading />
  const step = done ? 3 : preview ? 2 : 1
  const roleByCol = preview ? Object.fromEntries(Object.entries(preview.mapping).map(([r, c]) => [c, r])) : {}

  return (
    <>
      <PageHead title={t('Import a statement')} sub={t("Download a file from your bank's website and bring it in here. Duplicates are skipped, so overlapping date ranges are fine.")} />
      <div className="banner ca" style={{ marginBottom: 20 }}>
        <ShieldCheck />
        <div className="banner-body">
          <strong>{t('Your bank password stays with you.')}</strong> {t('For Canadian banks FinVault never connects to the bank.')}
          {' '}{t('The standard export files (QFX/OFX, QBO, QIF or CSV) are safest. Text-based PDFs can be imported too, but prefer')} <strong>QFX/OFX</strong>{t(": it's an open standard with stable transaction IDs, so re-imports never double-count.")}
        </div>
      </div>

      <ol className="steps move-steps" style={{ marginBottom: 16 }} aria-label={t('Steps')}>
        {[t('Choose account & file'), t('Check the preview'), t('Done')].map((l, i) => (
          <li key={l} className="row" style={{ gap: 8 }}>
            {i > 0 && <span className="step-sep" aria-hidden="true" />}
            <span className={`step ${step === i + 1 ? 'on' : step > i + 1 ? 'done' : ''}`} aria-current={step === i + 1 ? 'step' : undefined}><b>{i + 1}</b>{l}{step > i + 1 && <span className="sr"> ({t('done')})</span>}</span>
          </li>
        ))}
      </ol>

      {done && (
        <section className="card card-body row wrap" style={{ marginBottom: 20, gap: 16 }}>
          <Postmark top={account?.name ?? t('Statement')} date={new Date().toISOString()} bottom={t('SORTED')} />
          <div className="grow">
            <h2 ref={doneRef} tabIndex={-1}>{done.imported === 1 ? t('Imported {n} transaction', { n: done.imported }) : t('Imported {n} transactions', { n: done.imported })}</h2>
            <p className="muted">{done.skipped ? t('{n} already in FinVault were skipped.', { n: done.skipped }) + ' ' : ''}{done.transfers_matched ? (done.transfers_matched === 1 ? t('{n} transfer between your accounts matched.', { n: done.transfers_matched }) : t('{n} transfers between your accounts matched.', { n: done.transfers_matched })) + ' ' : ''}{t('Rules and remembered merchants categorized what they could.')}</p>
          </div>
          <Link to={`/transactions?uncategorized=1&account=${accountId}`} className="btn">{t('Review uncategorized')}</Link>
          <button className="btn primary" onClick={() => setDone(null)}><Upload />{t('Import another')}</button>
        </section>
      )}

      <div className="grid-2" style={{ gridTemplateColumns: preview ? 'minmax(0, 1fr)' : undefined }}>
        {!done && (
          <section className="card">
            <div className="card-head"><h2>{preview ? t('Preview') : t('Account and file')}</h2>{preview && <button className="btn sm ghost" onClick={() => { setPreview(null); setFile(null) }}>{t('Choose another file')}</button>}</div>
            <div className="card-body stack">
              {!preview && (
                <>
                  <Field label={t('Import into')}>
                    <div className="row">
                      <select className="input" required value={accountId} onChange={(e) => setAccountId(e.target.value)}
                        aria-invalid={!accountId && file ? true : undefined} aria-describedby={!accountId && file ? 'import-account-error' : undefined}>
                        <option value="">{t('Choose an account…')}</option>
                        {accts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.institution ? ` · ${a.institution}` : ''}</option>)}
                      </select>
                      <button className="btn" onClick={() => setAdding(true)}>{t('New account')}</button>
                    </div>
                  </Field>
                  {/* Works without dragging: it is a button that opens the file picker (Enter or Space). */}
                  <div className={`dropzone ${over ? 'over' : ''}`} role="button" tabIndex={0} aria-describedby="import-drop-hint"
                    onClick={() => inputRef.current?.click()} onKeyDown={activateOnKey(() => inputRef.current?.click())}
                    onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
                    onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]) }}>
                    <FileUp size={28} style={{ marginBottom: 8 }} />
                    <div><strong>{file ? file.name : t('Drop your statement file here')}</strong></div>
                    <div className="small" id="import-drop-hint">{file ? t('Reading…') : t('or click to choose · QFX, OFX, QBO, QIF, CSV, PDF')}</div>
                    <input ref={inputRef} type="file" hidden accept=".qfx,.ofx,.qbo,.qif,.csv,.txt,.tsv,.pdf,application/pdf" onChange={(e) => e.target.files[0] && setFile(e.target.files[0])} />
                  </div>
                  {!accountId && file && <p className="error-text" id="import-account-error" role="alert">{t('Choose which account this file belongs to.')}</p>}
                </>
              )}
              <div role="status">{busy && !preview && <div className="row muted"><Loader2 className="spin" size={16} />{t('Reading the file…')}</div>}</div>
              {error && <div className="banner warn" role="alert"><AlertTriangle /><div className="banner-body">{error}</div></div>}
              {preview && <Preview p={preview} account={account} options={options} change={change} setRole={setRole} roleByCol={roleByCol} presets={presetList} busy={busy} commit={commit} />}
            </div>
          </section>
        )}

        {!preview && (
          <section className="card">
            <div className="card-head"><h2>{preset && preset.id !== 'generic' ? t('How to download from {bank}', { bank: preset.name }) : t('How to download your statement')}</h2></div>
            <div className="card-body stack" style={{ gap: 14 }}>
              {preset ? (
                <>
                  <div className="row wrap" style={{ gap: 6 }}>
                    {preset.formats.map((f) => <span key={f} className={`pill ${f.startsWith('QFX') && preset.recommended === 'ofx' ? 'green' : ''}`}>{f}{f.startsWith('QFX') && preset.recommended === 'ofx' ? ` · ${t('recommended')}` : ''}</span>)}
                  </div>
                  {preset.notes && <p className="muted">{t(preset.notes)}</p>}
                </>
              ) : <p className="muted">{t('Pick an account with its bank set to see bank-specific notes.')}</p>}
              <ol className="howto">{(presetList[0]?.steps ?? []).map((s) => <li key={s}>{t(s)}</li>)}</ol>
              <p className="small muted"><Info size={13} style={{ verticalAlign: -2 }} /> {t('PDF imports are best-effort and work only when the statement contains selectable text. Menu names differ between banks and change over time.')}</p>
            </div>
          </section>
        )}
      </div>

      {!preview && (
        <Link to="/import/move" className="card move-link">
          <Truck aria-hidden="true" />
          <div className="grow">
            <div className="title">{t('Moving from another app?')}</div>
            <div className="meta">{t('Bring your whole history in once from YNAB, Actual Budget, Mint, Monarch Money or another app, with accounts, categories and transfers.')}</div>
          </div>
          <ArrowRight aria-hidden="true" />
        </Link>
      )}

      <WatchedFolder />

      <section className="card" style={{ marginTop: 20 }}>
        <div className="card-head"><h2>{t('Recent imports')}</h2></div>
        {!batches.data?.length ? <Empty icon={Upload} title={t('Nothing imported yet')} /> : (
          <div className="list">
            {batches.data.slice(0, 12).map((b) => (
              <div className="list-row" key={b.id}>
                <FileUp className="row-icon" aria-hidden="true" />
                <div className="grow">
                  <div className="title">{b.filename}</div>
                  <div className="meta">{b.account_name} · {b.format.toUpperCase()} · {date(b.created_at)} · {t('{n} added', { n: b.imported })}{b.skipped ? t(', {n} skipped', { n: b.skipped }) : ''}</div>
                </div>
                <button className="btn sm ghost" aria-label={t('Undo import of {file}', { file: b.filename })} onClick={() => setConfirm({ title: t('Undo this import?'), body: t('Removes the {n} transactions that came from {file}. Edits you made to them are lost.', { n: b.imported, file: b.filename }), action: t('Undo import'),
                  onConfirm: async () => { const r = await api.del(`/imports/batches/${b.id}`); toast(t('Removed {n} transactions', { n: r.removed })); bump() } })}><RotateCcw size={14} />{t('Undo')}</button>
              </div>
            ))}
          </div>
        )}
      </section>

      {adding && <AccountDialog account={{}} presets={presetList} onClose={() => setAdding(false)} onSaved={(a) => { bump(); if (a?.id) setAccountId(String(a.id)) }} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function Preview({ p, account, options, change, setRole, roleByCol, presets, busy, commit }) {
  const [showMapping, setShowMapping] = useState(p.format === 'csv' && (p.mapping.date === undefined || p.warnings.length > 0))
  return (
    <>
      <div className="stat-strip">
        <div><small>{t('Format')}</small><strong>{p.format.toUpperCase()}</strong></div>
        <div><small>{t('Transactions')}</small><strong>{p.total}</strong></div>
        <div><small>{t('New')}</small><strong className="income">{p.new}</strong></div>
        <div><small>{t('Already imported')}</small><strong className="muted">{p.duplicates}</strong></div>
        {p.date_range && <div><small>{t('Dates')}</small><strong style={{ fontSize: 15 }}>{date(p.date_range[0])} – {date(p.date_range[1])}</strong></div>}
        {p.statement_balance != null && <div><small>{t('Statement balance')}</small><strong><Money value={p.statement_balance} currency={account?.currency} /></strong></div>}
      </div>

      <p className="sr" role="status">{t('Preview ready: {n} new of {total}.', { n: p.new, total: p.total })}</p>
      {p.warnings.map((w) => <div className="banner warn" key={w}><AlertTriangle /><div className="banner-body">{serverText(w)}</div></div>)}

      <div className="row wrap" style={{ gap: 18 }}>
        {p.format === 'csv' && (
          <Field label={t('Bank layout')}>
            <select className="input sm" value={options.preset ?? p.preset ?? ''} onChange={(e) => change({ preset: e.target.value || null, mapping: null })} style={{ minWidth: 220 }}>
              <option value="">{t('Detect automatically')}</option>
              {presets.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </Field>
        )}
        {p.format !== 'ofx' && (
          <Field label={t('Date format')}>
            <select className="input sm" value={options.date_format ?? ''} onChange={(e) => change({ date_format: e.target.value || null })}>
              {DATE_FORMATS.map(([v, l]) => <option key={v} value={v}>{v ? l : t(l)}{!v && p.date_format ? ` (${DATE_FORMATS.find((d) => d[0] === p.date_format)?.[1] ?? p.date_format})` : ''}</option>)}
            </select>
          </Field>
        )}
        <label className="row" style={{ gap: 10, marginTop: 20 }}>
          <Switch checked={p.inverted} onChange={(v) => change({ invert: v })} label={t('Flip signs')} />
          <span><span className="strong">{t('Flip signs')}</span><br /><span className="small muted">{t('Use when purchases show up as money in.')}</span></span>
        </label>
        {p.format === 'csv' && <button className="link-btn" style={{ marginTop: 20 }} aria-expanded={showMapping} onClick={() => setShowMapping((s) => !s)}>{showMapping ? t('Hide column mapping') : t('Edit column mapping')}</button>}
      </div>

      {showMapping && p.format === 'csv' && (
        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-body">
            <p className="small muted" style={{ marginBottom: 12 }}>{t('Tell FinVault what each column holds. You need a date and either an amount or money out / money in.')}</p>
            <div className="mapping-grid">
              {p.columns.map((col, i) => (
                <Field key={i} label={col || t('Column {n}', { n: i + 1 })} hint={p.sample_rows[0]?.[i] ? t('e.g. {value}', { value: p.sample_rows[0][i].slice(0, 28) }) : t('empty')}>
                  <select className="input sm" value={roleByCol[i] ?? ''} onChange={(e) => setRole(i, e.target.value)}>
                    <option value="">{t('Ignore')}</option>
                    {Object.entries(ROLE_LABELS).map(([r, l]) => <option key={r} value={r}>{l}</option>)}
                  </select>
                </Field>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="table-wrap card" style={{ boxShadow: 'none', maxHeight: 460, overflowY: 'auto' }} tabIndex={0} role="region" aria-label={t('Preview')}>
        <table className="table">
          <thead><tr><th scope="col">{t('Date')}</th><th scope="col">{t('Description')}</th><th scope="col" className="hide-sm">{t('Category')}</th><th scope="col" className="amount">{t('Amount')}</th><th scope="col"><span className="sr">{t('Status')}</span></th></tr></thead>
          <tbody>
            {p.rows.map((r, i) => (
              <tr key={i} className={r.duplicate ? 'dup' : ''}>
                <td className="num" style={{ whiteSpace: 'nowrap' }}>{date(r.date)}</td>
                <td className="desc"><div>{r.description}</div>{r.bank_category && <small>{t('Bank: {category}', { category: r.bank_category })}</small>}</td>
                <td className="hide-sm">{r.category ? <span className="row" style={{ gap: 6 }}>{r.category}<span className="pill">{r.category_source === 'history' ? t('remembered') : t('rule')}</span></span> : <span className="muted">—</span>}</td>
                <td className="amount"><Money value={r.amount} currency={account?.currency} sign colored /></td>
                <td>{r.duplicate && <span className="pill">{t('already imported')}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {p.total > p.rows.length && <p className="small muted">{t('Showing the first {n} of {total}.', { n: p.rows.length, total: p.total })}</p>}

      <div className="row wrap">
        <span className="muted small">{t('Into')} <strong style={{ color: 'var(--fg)' }}>{account?.name}</strong> ({account?.currency})</span>
        <span className="spacer" />
        <button className="btn primary" onClick={commit} disabled={busy || p.new === 0} style={{ height: 40 }}>
          {busy ? <Loader2 className="spin" size={16} /> : <ArrowRight size={16} />}
          {p.new === 0 ? t('Nothing new to import') : p.new === 1 ? t('Import {n} transaction', { n: p.new }) : t('Import {n} transactions', { n: p.new })}
        </button>
      </div>
    </>
  )
}
