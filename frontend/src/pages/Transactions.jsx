import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowLeftRight, Download, Filter, Paperclip, Pencil, Plus, Search, SlidersHorizontal, Split, Trash2, Upload, Users, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, qs } from '../api'
import { useApp } from '../context'
import { Confirm, Empty, ErrorNote, Money, PageHead, useData, useToast, CategoryTile } from '../components/ui'
import TxDialog, { CategorySelect } from '../components/TxDialog'
import RuleDialog from '../components/RuleDialog'
import TransferReview from '../components/TransferReview'
import { date } from '../lib/format'
import { t } from '../i18n'

function monthRange(ym) {
  if (!ym) return {}
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  return { start: `${ym}-01`, end: `${ym}-${String(last).padStart(2, '0')}` }
}

export default function Transactions() {
  const [params, setParams] = useSearchParams()
  const { version, bump } = useApp()
  const toast = useToast()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [showFilters, setShowFilters] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [ruleFrom, setRuleFrom] = useState(null)
  const [ruleOpen, setRuleOpen] = useState(false)
  const [reviewing, setReviewing] = useState(false)

  const filters = useMemo(() => {
    const month = monthRange(params.get('month'))
    return {
      q: params.get('q') || undefined,
      account_id: params.getAll('account').map(Number),
      category_id: params.getAll('category').map(Number),
      uncategorized: params.get('uncategorized') === '1',
      start: params.get('start') || month.start, end: params.get('end') || month.end,
      kind: params.get('kind') || undefined,
      min_amount: params.get('min') || undefined, max_amount: params.get('max') || undefined,
      page: Number(params.get('page') || 1), page_size: 50,
    }
  }, [params])

  const accounts = useData(() => api.get('/accounts'), [version])
  const categories = useData(() => api.get('/categories'), [version])
  const list = useData(() => api.get(`/transactions${qs(filters)}`), [filters, version])
  const pairs = useData(() => api.get('/transfers/suggestions'), [version])

  useEffect(() => {
    const timer = setTimeout(() => update({ q: q || null }), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])
  useEffect(() => setSelected(new Set()), [filters])

  function update(changes) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      next.delete(k)
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x))
      else if (v !== null && v !== undefined && v !== '') next.set(k, v)
    }
    if (!('page' in changes)) next.delete('page')
    if (next.toString() !== params.toString()) setParams(next, { replace: true })
  }

  const cats = categories.data ?? []
  const accts = accounts.data?.items ?? []
  const items = list.data?.items ?? []
  const activeFilters = [
    ...filters.account_id.map((id) => ({ key: `a${id}`, label: accts.find((a) => a.id === id)?.name ?? t('Account'), clear: { account: filters.account_id.filter((x) => x !== id) } })),
    ...filters.category_id.map((id) => ({ key: `c${id}`, label: cats.find((c) => c.id === id)?.name ?? t('Category'), clear: { category: filters.category_id.filter((x) => x !== id) } })),
    filters.uncategorized && { key: 'u', label: t('Uncategorized'), clear: { uncategorized: null } },
    (filters.start || filters.end) && { key: 'd', label: `${filters.start ? date(filters.start) : '…'} – ${filters.end ? date(filters.end) : '…'}`, clear: { start: null, end: null, month: null } },
    filters.kind && { key: 'k', label: filters.kind === 'income' ? t('Money in') : t('Money out'), clear: { kind: null } },
  ].filter(Boolean)

  const setCategory = async (tx, category_id) => {
    try {
      await api.patch(`/transactions/${tx.id}`, { category_id })
      list.reload()
      bump()
      if (category_id && !tx.category_id) setRuleFrom({ tx, category_id })
    } catch (e) { toast(e.message, 'error') }
  }

  const bulk = async (action, category_id) => {
    const ids = [...selected]
    await api.post('/transactions/bulk', { ids, action, category_id })
    toast(action === 'delete' ? t('Deleted {n} transactions', { n: ids.length }) : t('Categorized {n} transactions', { n: ids.length }))
    list.reload(); bump()
  }

  const exportUrl = (format) => `/api/transactions/export${qs({ ...filters, page: undefined, page_size: undefined, format })}`
  const allSelected = items.length > 0 && items.every((tx) => selected.has(tx.id))
  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / filters.page_size))

  return (
    <>
      <PageHead title={t('Transactions')}>
        <div className="segmented" role="group" aria-label={t('Export')}>
          <a className="btn ghost sm" href={exportUrl('csv')}><Download />CSV</a>
          <a className="btn ghost sm" href={exportUrl('ofx')}>OFX</a>
          <a className="btn ghost sm" href={exportUrl('json')}>JSON</a>
        </div>
        <Link to="/import" className="btn"><Upload />{t('Import')}</Link>
        <button className="btn primary" onClick={() => setEditing({})} disabled={!accts.length}><Plus />{t('Add transaction')}</button>
      </PageHead>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ padding: 14 }}>
          <div className="row wrap">
            <div className="search-box">
              <Search />
              <input className="input" placeholder={t('Search descriptions, payees and notes…')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('Search transactions')} />
            </div>
            <button className={`btn ${showFilters ? 'primary' : ''}`} onClick={() => setShowFilters((s) => !s)}><Filter />{t('Filters')}</button>
            {activeFilters.length > 0 && <button className="btn ghost sm" onClick={() => setParams({}, { replace: true })}>{t('Clear filters')}</button>}
          </div>
          {showFilters && (
            <div className="form-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', marginTop: 14 }}>
              <label className="field"><span>{t('Account')}</span>
                <select className="input sm" value={filters.account_id[0] ?? ''} onChange={(e) => update({ account: e.target.value ? [e.target.value] : [] })}>
                  <option value="">{t('All accounts')}</option>{accts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select></label>
              <label className="field"><span>{t('Category')}</span>
                <select className="input sm" value={filters.uncategorized ? 'none' : filters.category_id[0] ?? ''}
                  onChange={(e) => e.target.value === 'none' ? update({ uncategorized: '1', category: [] }) : update({ category: e.target.value ? [e.target.value] : [], uncategorized: null })}>
                  <option value="">{t('All categories')}</option><option value="none">{t('Uncategorized')}</option>
                  {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select></label>
              <label className="field"><span>{t('From')}</span><input className="input sm" type="date" value={filters.start ?? ''} onChange={(e) => update({ start: e.target.value, month: null })} /></label>
              <label className="field"><span>{t('To')}</span><input className="input sm" type="date" value={filters.end ?? ''} onChange={(e) => update({ end: e.target.value, month: null })} /></label>
              <label className="field"><span>{t('Direction')}</span>
                <select className="input sm" value={filters.kind ?? ''} onChange={(e) => update({ kind: e.target.value })}>
                  <option value="">{t('In and out')}</option><option value="expense">{t('Money out')}</option><option value="income">{t('Money in')}</option>
                </select></label>
              <label className="field"><span>{t('Amount at least')}</span><input className="input sm" type="number" min="0" value={filters.min_amount ?? ''} onChange={(e) => update({ min: e.target.value })} /></label>
            </div>
          )}
          {activeFilters.length > 0 && (
            <div className="row wrap" style={{ marginTop: 12, gap: 6 }}>
              {activeFilters.map((f) => (
                <span key={f.key} className="pill indigo" style={{ padding: '3px 6px 3px 10px' }}>{f.label}
                  <button className="icon-btn" style={{ width: 18, height: 18 }} onClick={() => update(f.clear)} aria-label={t('Remove {label} filter', { label: f.label })}><X size={12} /></button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <ErrorNote error={list.error} />
      {pairs.data?.length > 0 && (
        <div className="banner info" style={{ marginBottom: 16 }}>
          <ArrowLeftRight />
          <div className="banner-body"><strong>{pairs.data.length === 1 ? t('{n} possible transfer between your accounts.', { n: pairs.data.length }) : t('{n} possible transfers between your accounts.', { n: pairs.data.length })}</strong> {t('Matching them keeps card payments and savings moves out of your spending.')}</div>
          <button className="btn sm primary" onClick={() => setReviewing(true)}>{t('Review')}</button>
        </div>
      )}
      {ruleFrom && !ruleOpen && (
        <div className="banner ca" style={{ marginBottom: 16 }}>
          <SlidersHorizontal />
          <div className="banner-body">
            {t('Always put transactions like')} <strong>{ruleFrom.tx.payee || ruleFrom.tx.description}</strong> {t('in')}{' '}
            <strong>{cats.find((c) => c.id === ruleFrom.category_id)?.name}</strong>{t('?')}
          </div>
          <button className="btn sm primary" onClick={() => setRuleOpen(true)}>{t('Create rule')}</button>
          <button className="icon-btn" onClick={() => setRuleFrom(null)} aria-label={t('Dismiss')}><X /></button>
        </div>
      )}
      <section className="card">
        {selected.size > 0 ? (
          <div className="card-head" style={{ background: 'var(--accent)', borderTopLeftRadius: 'inherit', borderTopRightRadius: 'inherit' }}>
            <strong>{t('{n} selected', { n: selected.size })}</strong>
            <div className="row wrap">
              <CategorySelect className="input sm" categories={cats} value={null} placeholder={t('Set category…')} onChange={(v) => v && bulk('categorize', v)} style={{ width: 200 }} />
              <button className="btn sm danger" onClick={() => setConfirm({ title: t('Delete {n} transactions?', { n: selected.size }), body: t('This removes them from FinVault. Re-importing the same file would bring them back.'), onConfirm: () => bulk('delete') })}><Trash2 />{t('Delete')}</button>
              <button className="btn sm ghost" onClick={() => setSelected(new Set())}>{t('Cancel')}</button>
            </div>
          </div>
        ) : (
          <div className="card-head">
            <div className="row" style={{ gap: 18 }}>
              <span className="muted">{total === 1 ? t('{n} transaction', { n: total.toLocaleString() }) : t('{n} transactions', { n: total.toLocaleString() })}</span>
              {total > 0 && <>
                <span className="small">{t('In')} <Money value={list.data.inflow} currency={accts[0]?.currency ?? 'CAD'} className="income strong" /></span>
                <span className="small">{t('Out')} <Money value={list.data.outflow} currency={accts[0]?.currency ?? 'CAD'} className="expense strong" /></span>
              </>}
            </div>
            <Link to="/rules" className="small row" style={{ gap: 5 }}><SlidersHorizontal size={14} />{t('Rules')}</Link>
          </div>
        )}
        {list.data && items.length === 0 ? (
          accts.length === 0
            ? <Empty title={t('Add an account first')} action={<Link className="btn primary" to="/accounts">{t('Add an account')}</Link>}>{t('Transactions belong to an account, like your chequing or a credit card.')}</Empty>
            : <Empty icon={Search} title={activeFilters.length || filters.q ? t('No transactions match') : t('No transactions yet')}
                action={!(activeFilters.length || filters.q) && <Link className="btn primary" to="/import"><Upload />{t('Import a statement')}</Link>}>
                {activeFilters.length || filters.q ? t('Try a different search or clear the filters.') : t('Import a QFX, OFX or CSV file from your bank, or add one by hand.')}
              </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr>
                <th style={{ width: 36 }}><input type="checkbox" checked={allSelected} aria-label={t('Select all')}
                  onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((tx) => tx.id)))} /></th>
                <th>{t('Date')}</th><th>{t('Description')}</th><th className="hide-sm">{t('Account')}</th><th>{t('Category')}</th><th className="amount">{t('Amount')}</th><th style={{ width: 72 }} />
              </tr></thead>
              <tbody>
                {items.map((tx) => (
                  <tr key={tx.id}>
                    <td><input type="checkbox" checked={selected.has(tx.id)} aria-label={t('Select {name}', { name: tx.description })}
                      onChange={() => { const s = new Set(selected); s.has(tx.id) ? s.delete(tx.id) : s.add(tx.id); setSelected(s) }} /></td>
                    <td className="num" style={{ whiteSpace: 'nowrap' }}>{date(tx.date, { month: 'short', day: 'numeric', year: 'numeric' })}</td>
                    <td className="desc">
                      <div className="row" style={{ gap: 10 }}>
                        <CategoryTile size="sm" name={tx.category_name} color={tx.category_color} />
                        <div style={{ minWidth: 0 }}>
                          <div title={tx.description}>{tx.payee || tx.description}</div>
                          {tx.payee && tx.payee !== tx.description && <small>{tx.description}</small>}
                          {tx.notes && <small> · {tx.notes}</small>}
                        </div>
                        <span className="tx-flags">
                          {tx.transfer_id && <button className="flag" title={t('Matched transfer')} aria-label={t('Matched transfer')} onClick={() => setEditing({ ...tx, _tab: 'details' })}><ArrowLeftRight /></button>}
                          {tx.split && <button className="flag" title={t('Split')} aria-label={t('Split')} onClick={() => setEditing({ ...tx, _tab: 'split' })}><Split /></button>}
                          {tx.shared > 0 && <button className="flag" title={t('Shared')} aria-label={t('Shared')} onClick={() => setEditing({ ...tx, _tab: 'share' })}><Users /></button>}
                          {tx.attachments > 0 && <button className="flag" title={t('Receipt')} aria-label={t('Receipt')} onClick={() => setEditing({ ...tx, _tab: 'receipts' })}><Paperclip /></button>}
                        </span>
                      </div>
                    </td>
                    <td className="hide-sm muted">{tx.account_name}</td>
                    <td>
                      <CategorySelect className={`cat-select ${tx.category_id ? '' : 'unset'}`} categories={cats} value={tx.category_id}
                        onChange={(v) => setCategory(tx, v)} aria-label={t('Category')} />
                    </td>
                    <td className="amount"><Money value={tx.amount} currency={tx.currency} sign colored /></td>
                    <td>
                      <div className="row" style={{ gap: 0, justifyContent: 'flex-end' }}>
                        <button className="icon-btn" onClick={() => setEditing(tx)} aria-label={t('Edit')}><Pencil /></button>
                        <button className="icon-btn" onClick={() => setConfirm({ title: t('Delete this transaction?'), body: tx.description,
                          onConfirm: async () => { await api.del(`/transactions/${tx.id}`); list.reload(); bump() } })} aria-label={t('Delete')}><Trash2 /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="pager">
            <span>{t('Page {page} of {pages}', { page: filters.page, pages })}</span>
            <div className="row">
              <button className="btn sm" disabled={filters.page <= 1} onClick={() => update({ page: filters.page - 1 })}>{t('Previous')}</button>
              <button className="btn sm" disabled={filters.page >= pages} onClick={() => update({ page: filters.page + 1 })}>{t('Next')}</button>
            </div>
          </div>
        )}
      </section>

      {editing && <TxDialog tx={editing} initialTab={editing._tab} accounts={accts} categories={cats} onClose={() => setEditing(null)} onSaved={() => { list.reload(); bump() }} />}
      {reviewing && <TransferReview pairs={pairs.data ?? []} onClose={() => { setReviewing(false); pairs.reload() }} onDone={() => { list.reload(); bump() }} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
      {ruleFrom && ruleOpen && (
        <RuleDialog categories={cats} accounts={accts} suggestFrom={ruleFrom} onClose={() => { setRuleOpen(false); setRuleFrom(null) }}
          onSaved={(r) => { list.reload(); bump(); if (r.applied) toast(t('Rule saved and applied to {n} more transactions', { n: r.applied })) }} />
      )}
    </>
  )
}
