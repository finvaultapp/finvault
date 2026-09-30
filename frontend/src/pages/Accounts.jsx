import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Archive, ArchiveRestore, Pencil, Plus, Scale, Trash2, Upload, Wallet } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import Postmark from '../components/Postmark'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { ACCOUNT_TYPES, CURRENCIES, date, todayISO } from '../lib/format'
import { t } from '../i18n'


export default function Accounts() {
  const { version, bump } = useApp()
  const accounts = useData(() => api.get('/accounts'), [version])
  const presets = useData(() => api.get('/imports/presets'), [])
  const [editing, setEditing] = useState(null)
  const [reconcile, setReconcile] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [showArchived, setShowArchived] = useState(false)

  if (!accounts.data) return <Loading />
  const { items, base_currency, warnings } = accounts.data
  const visible = items.filter((a) => showArchived || !a.is_archived)
  const presetName = Object.fromEntries((presets.data?.presets ?? []).map((p) => [p.id, p.name]))
  const archivedCount = items.filter((a) => a.is_archived).length

  return (
    <>
      <PageHead title={t('Accounts')} sub={t('Chequing, savings, credit cards and loans. Balances come from your opening balance plus every imported transaction.')}>
        {archivedCount > 0 && <button className="btn ghost" onClick={() => setShowArchived((s) => !s)}>{showArchived ? t('Hide archived ({n})', { n: archivedCount }) : t('Show archived ({n})', { n: archivedCount })}</button>}
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add account')}</button>
      </PageHead>
      <div className="stack">
        <Warnings items={warnings} />
        <section className="card">
          {visible.length === 0 ? (
            <Empty icon={Wallet} title={t('No accounts yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add your first account')}</button>}>
              {t("Add each account you want to track. You'll import its transactions from your bank's export file.")}
            </Empty>
          ) : (
            <div className="list">
              {visible.map((a) => {
                return (
                  <div className="list-row" key={a.id} style={{ opacity: a.is_archived ? 0.6 : 1 }}>
                    {a.last_transaction
                      ? <Postmark className="postmark mini" top={a.name} date={a.last_transaction} />
                      : <span className="postmark-blank" title={t('no transactions yet')} aria-hidden="true" />}
                    <div className="grow">
                      <div className="row" style={{ gap: 8 }}>
                        <Link to={`/transactions?account=${a.id}`} className="title" style={{ color: 'inherit' }}>{a.name}</Link>
                        {a.country === 'CA' && <span className="pill" title={t('Canadian account: imported from files, never connected to the bank')}>{t('Import only')}</span>}
                        {a.synced && <span className="pill blue">{t('Synced')}</span>}
                        {a.is_archived && <span className="pill">{t('Archived')}</span>}
                      </div>
                      <div className="meta">
                        {[a.institution || presetName[a.import_preset], ACCOUNT_TYPES[a.type], a.currency].filter(Boolean).join(' · ')}
                        {' · '}{a.last_transaction ? t('last transaction {date}', { date: date(a.last_transaction) }) : t('no transactions yet')}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className="strong"><Money value={a.balance} currency={a.currency} colored={a.balance < 0} /></div>
                      {a.currency !== base_currency && (
                        <div className="meta">{a.balance_converted == null ? t('no rate') : <Money value={a.balance_converted} currency={base_currency} />}</div>
                      )}
                      {a.holdings_value != null && (
                        <div className="meta"><Link to="/investments" style={{ color: 'inherit' }}>{t('cash')} <Money value={a.cash_balance} currency={a.currency} /> · {t('holdings')} <Money value={a.holdings_value} currency={a.currency} /></Link></div>
                      )}
                    </div>
                    <div className="actions">
                      <Link className="icon-btn" to={`/import?account=${a.id}`} aria-label={t('Import')} title={t('Import a statement')}><Upload /></Link>
                      <button className="icon-btn" onClick={() => setReconcile(a)} aria-label={t('Match statement balance')} title={t("Match your statement's balance")}><Scale /></button>
                      <button className="icon-btn" onClick={() => setEditing(a)} aria-label={t('Edit {name}', { name: a.name })}><Pencil /></button>
                      <button className="icon-btn" aria-label={a.is_archived ? t('Unarchive') : t('Archive')} title={a.is_archived ? t('Unarchive') : t('Archive')}
                        onClick={async () => { await api.patch(`/accounts/${a.id}`, { is_archived: !a.is_archived }); bump() }}>
                        {a.is_archived ? <ArchiveRestore /> : <Archive />}
                      </button>
                      <button className="icon-btn" aria-label={t('Delete {name}', { name: a.name })} onClick={() => setConfirm({ title: t('Delete {name}?', { name: a.name }),
                        body: t('This permanently removes the account and its {n} transactions. Archive it instead to keep the history.', { n: a.transaction_count }),
                        onConfirm: async () => { await api.del(`/accounts/${a.id}`); bump() } })}><Trash2 /></button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
      {editing && <AccountDialog account={editing} presets={presets.data?.presets ?? []} onClose={() => setEditing(null)} onSaved={bump} />}
      {reconcile && <ReconcileDialog account={reconcile} onClose={() => setReconcile(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

export function AccountDialog({ account, presets, onClose, onSaved }) {
  const toast = useToast()
  const { user } = useApp()
  const editing = !!account.id
  const [f, setF] = useState({
    name: account.name ?? '', institution: account.institution ?? '', type: account.type ?? 'checking',
    currency: account.currency ?? user.base_currency, country: account.country ?? 'CA',
    opening_balance: account.opening_balance ?? 0, opening_date: account.opening_date ?? '', import_preset: account.import_preset ?? '',
  })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const pickBank = (e) => {
    const p = presets.find((x) => x.id === e.target.value)
    setF({ ...f, import_preset: e.target.value, institution: p && p.id !== 'generic' ? p.name : f.institution, country: p?.country ?? f.country })
  }
  const save = async () => {
    const body = { ...f, opening_balance: Number(f.opening_balance) || 0, opening_date: f.opening_date || null, import_preset: f.import_preset || null }
    try {
      const saved = editing ? await api.patch(`/accounts/${account.id}`, body) : await api.post('/accounts', body)
      toast(editing ? t('Account updated') : t('Account added'))
      onSaved(saved); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  const ca = presets.filter((p) => p.country === 'CA')
  return (
    <Dialog title={editing ? t('Edit account') : t('Add account')} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className="btn primary" onClick={save} disabled={!f.name}>{t('Save')}</button>
    </>}>
      <div className="form-grid">
        <Field label={t('Bank or card')} className="full" hint={t("Used to read your bank's export file layout.")}>
          <select className="input" value={f.import_preset} onChange={pickBank}>
            <option value="">{t('Choose…')}</option>
            <optgroup label={t('Canada')}>{ca.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</optgroup>
            <optgroup label={t('Other')}>{presets.filter((p) => p.country !== 'CA').map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</optgroup>
          </select>
        </Field>
        <Field label={t('Account name')} className="full"><input className="input" value={f.name} onChange={set('name')} placeholder={t('e.g. Joint chequing')} /></Field>
        <Field label={t('Type')}><select className="input" value={f.type} onChange={set('type')}>
          {Object.entries(ACCOUNT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label={t('Currency')}><select className="input" value={f.currency} onChange={set('currency')}>
          {CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label={t('Opening balance')} hint={f.type === 'credit_card' || f.type === 'loan' ? t('Enter what you owe as a negative number.') : t('Balance before the first imported transaction.')}>
          <input className="input" type="number" step="0.01" value={f.opening_balance} onChange={set('opening_balance')} /></Field>
        <Field label={t('Opening date')} hint={t('Optional')}><input className="input" type="date" value={f.opening_date ?? ''} onChange={set('opening_date')} /></Field>
        <Field label={t('Country')}><select className="input" value={f.country} onChange={set('country')}>
          <option value="CA">{t('Canada')}</option><option value="US">{t('United States')}</option><option value="BR">{t('Brazil')}</option><option value="EU">{t('Europe')}</option><option value="">{t('Other')}</option></select></Field>
        <Field label={t('Institution name')} hint={t('Shown under the account name.')}><input className="input" value={f.institution} onChange={set('institution')} /></Field>
        {f.country === 'CA' && (
          <div className="full banner ca"><Upload />
            <div className="banner-body">{t('Canadian accounts are')} <strong>{t('import only')}</strong>{t('. FinVault never asks for your online-banking password and never connects to the bank; you download your statement file and import it.')}</div>
          </div>
        )}
      </div>
    </Dialog>
  )
}

function ReconcileDialog({ account, onClose, onSaved }) {
  const toast = useToast()
  const [balance, setBalance] = useState('')
  const [on, setOn] = useState(todayISO())
  const save = async () => {
    try {
      const r = await api.post(`/accounts/${account.id}/reconcile`, { balance: Number(balance), on })
      toast(r.adjusted_by ? t('Opening balance adjusted by {amount}', { amount: r.adjusted_by.toFixed(2) }) : t('Already matches your statement'))
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={t("Match {name}'s balance", { name: account.name })} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={balance === ''}>{t('Match')}</button>
    </>}>
      <p className="muted" style={{ marginBottom: 14 }}>{t('Enter the balance your bank shows on a statement date. FinVault adjusts the opening balance so both agree. Transactions stay untouched.')}</p>
      <div className="form-grid">
        <Field label={t('Statement balance')}><input className="input" type="number" step="0.01" value={balance} onChange={(e) => setBalance(e.target.value)} /></Field>
        <Field label={t('On date')}><input className="input" type="date" value={on} onChange={(e) => setOn(e.target.value)} /></Field>
      </div>
      <p className="small muted" style={{ marginTop: 12 }}>{t('FinVault currently shows')} <Money value={account.cash_balance ?? account.balance} currency={account.currency} /> {t('as of today.')}</p>
      {account.holdings_value != null && <p className="small muted">{t('This matches the cash balance only; holdings are valued on the Investments page.')}</p>}
    </Dialog>
  )
}
