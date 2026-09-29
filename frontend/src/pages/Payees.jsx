import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Combine, Pencil, Search, Store, Tags as TagsIcon, Trash2 } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { CategoryTile, Confirm, Dialog, Empty, ErrorNote, Field, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { CategorySelect } from '../components/TxDialog'
import { TagPill } from '../components/Tags'
import { date } from '../lib/format'
import { t } from '../i18n'

const SORTS = () => [['-count', t('Most transactions')], ['-total', t('Most money')], ['-last', t('Seen most recently')], ['name', t('Name')]]
const PAGE = 50

export default function Payees() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'tags' ? 'tags' : 'payees'
  const setTab = (v) => setParams(v === 'tags' ? { tab: 'tags' } : {}, { replace: true })
  return (
    <>
      <PageHead title={t('Payees')} sub={t('Clean up messy merchant names in one place. Payees are grouped by the merchant in the bank’s description, so store numbers and card digits don’t split them.')}>
        <div className="segmented" role="tablist" aria-label={t('Payees and tags')}>
          <button role="tab" aria-selected={tab === 'payees'} className={tab === 'payees' ? 'on' : ''} onClick={() => setTab('payees')}>{t('Payees')}</button>
          <button role="tab" aria-selected={tab === 'tags'} className={tab === 'tags' ? 'on' : ''} onClick={() => setTab('tags')}>{t('Tags')}</button>
        </div>
      </PageHead>
      {tab === 'tags' ? <TagManager /> : <PayeeList params={params} setParams={setParams} />}
    </>
  )
}

function PayeeList({ params, setParams }) {
  const { version, bump } = useApp()
  const toast = useToast()
  const [q, setQ] = useState(params.get('q') ?? '')
  const sort = params.get('sort') || '-count'
  const page = Number(params.get('page') || 1)
  const [selected, setSelected] = useState(new Map()) // key -> payee name
  const [renaming, setRenaming] = useState(null)
  const query = useMemo(() => ({ q: params.get('q') || undefined, sort, page, page_size: PAGE }), [params, sort, page])
  const list = useData(() => api.get(`/payees${qs(query)}`), [query, version])
  const cats = useData(() => api.get('/categories'), [version])

  const update = (changes) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) { next.delete(k); if (v) next.set(k, v) }
    if (!('page' in changes)) next.delete('page')
    if (next.toString() !== params.toString()) setParams(next, { replace: true })
  }
  useEffect(() => {
    const timer = setTimeout(() => update({ q: q.trim() || null }), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const setDefault = async (p, category_id) => {
    try {
      const r = await api.put('/payees/category', { keys: [p.key], category_id, apply: 'uncategorized' })
      toast(category_id == null ? t('Default category removed for {name}', { name: p.payee })
        : r.updated ? t('Default category saved. Sorted {n} uncategorized transactions.', { n: r.updated }) : t('Default category saved. Future imports will use it.'))
      list.reload(); bump()
    } catch (e) { toast(e.message, 'error') }
  }
  const toggle = (p) => {
    const next = new Map(selected)
    next.has(p.key) ? next.delete(p.key) : next.set(p.key, p.payee)
    setSelected(next)
  }

  if (!list.data || !cats.data) return <><ErrorNote error={list.error} /><Loading rows={6} /></>
  const d = list.data
  const pages = Math.max(1, Math.ceil(d.total / PAGE))
  const items = d.items
  const allSelected = items.length > 0 && items.every((p) => selected.has(p.key))

  return (
    <div className="stack">
      <Warnings items={d.warnings} />
      <div className="card"><div className="card-body" style={{ padding: 14 }}>
        <div className="row wrap">
          <div className="search-box"><Search /><input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search payees and bank descriptions…')} aria-label={t('Search payees')} /></div>
          <select className="input" style={{ width: 210 }} value={sort} onChange={(e) => update({ sort: e.target.value === '-count' ? null : e.target.value })} aria-label={t('Sort by')}>
            {SORTS().map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div></div>
      <section className="card">
        {selected.size > 0 ? (
          <div className="card-head bulk-head">
            <strong>{t('{n} selected', { n: selected.size })}</strong>
            <div className="row wrap">
              <button className="btn sm primary" onClick={() => setRenaming({ keys: [...selected.keys()], name: [...selected.values()][0] })}>
                {selected.size > 1 ? <><Combine />{t('Merge into one payee')}</> : <><Pencil />{t('Rename')}</>}
              </button>
              <button className="btn sm ghost" onClick={() => setSelected(new Map())}>{t('Cancel')}</button>
            </div>
          </div>
        ) : (
          <div className="card-head"><span className="muted">{d.total === 1 ? t('{n} payee', { n: d.total }) : t('{n} payees', { n: d.total.toLocaleString() })}</span>
            <span className="small muted">{t('Select several to merge them into one name.')}</span></div>
        )}
        {items.length === 0 ? (
          <Empty icon={Store} title={query.q ? t('No payees match') : t('No payees yet')}>{query.q ? t('Try a different search.') : t('Import a statement and every merchant shows up here.')}</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table payee-table">
              <thead><tr>
                <th style={{ width: 36 }}><input type="checkbox" checked={allSelected} aria-label={t('Select all')}
                  onChange={() => { const next = new Map(selected); items.forEach((p) => (allSelected ? next.delete(p.key) : next.set(p.key, p.payee))); setSelected(next) }} /></th>
                <th>{t('Payee')}</th><th className="amount">{t('Transactions')}</th><th className="amount">{t('Total')}</th>
                <th className="hide-sm">{t('Last seen')}</th><th className="hide-sm">{t('Usual category')}</th><th>{t('Default category')}</th><th style={{ width: 44 }} />
              </tr></thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.key}>
                    <td><input type="checkbox" checked={selected.has(p.key)} onChange={() => toggle(p)} aria-label={t('Select {name}', { name: p.payee })} /></td>
                    <td className="desc">
                      <div title={p.examples.join('\n')}><Link to={`/transactions${qs({ q: p.examples[0] })}`} style={{ color: 'inherit' }}>{p.payee}</Link></div>
                      <small>{p.key}{p.payee_variants > 1 ? ` · ${t('{n} spellings', { n: p.payee_variants })}` : ''}{p.rule?.set_payee ? ` · ${t('renamed on import')}` : ''}</small>
                    </td>
                    <td className="amount num" style={{ fontWeight: 500 }}>{p.count}</td>
                    <td className="amount"><Money value={p.total} currency={d.currency} colored /></td>
                    <td className="hide-sm muted num" style={{ whiteSpace: 'nowrap' }}>{p.last_seen ? date(p.last_seen) : '—'}</td>
                    <td className="hide-sm">{p.usual_category ? <span className="row" style={{ gap: 8 }}><CategoryTile size="sm" name={p.usual_category.name} color={p.usual_category.color} /><span className="small">{p.usual_category.name}</span></span> : <span className="muted small">—</span>}</td>
                    <td><CategorySelect className="input sm" categories={cats.data} value={p.rule?.set_category_id ?? null} placeholder={t('No default')}
                      onChange={(v) => setDefault(p, v)} aria-label={t('Default category for {name}', { name: p.payee })} style={{ minWidth: 150 }} /></td>
                    <td><button className="icon-btn" onClick={() => setRenaming({ keys: [p.key], name: p.payee })} aria-label={t('Rename {name}', { name: p.payee })}><Pencil /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="pager">
            <span>{t('Page {page} of {pages}', { page, pages })}</span>
            <div className="row">
              <button className="btn sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>{t('Previous')}</button>
              <button className="btn sm" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>{t('Next')}</button>
            </div>
          </div>
        )}
      </section>
      {renaming && <RenameDialog {...renaming} onClose={() => setRenaming(null)} onDone={() => { setSelected(new Map()); list.reload(); bump() }} />}
    </div>
  )
}

function RenameDialog({ keys, name, onClose, onDone }) {
  const toast = useToast()
  const [payee, setPayee] = useState(name ?? '')
  const [rule, setRule] = useState(true)
  const [busy, setBusy] = useState(false)
  const merge = keys.length > 1
  const save = async () => {
    setBusy(true)
    try {
      const r = await api.post('/payees/rename', { keys, payee, create_rule: rule })
      toast(t('Renamed {n} transactions to “{name}”', { n: r.updated, name: payee.trim() }))
      onDone(); onClose()
    } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }
  return (
    <Dialog title={merge ? t('Merge {n} payees', { n: keys.length }) : t('Rename payee')} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={busy || !payee.trim()} onClick={save}>{merge ? t('Merge') : t('Rename')}</button></>}>
      <div className="stack" style={{ gap: 14 }}>
        <Field label={t('Payee name')} hint={merge ? t('Every transaction from these merchants gets this name.') : t('Every transaction from this merchant gets this name.')}>
          <input className="input" value={payee} onChange={(e) => setPayee(e.target.value)} maxLength={200} onKeyDown={(e) => e.key === 'Enter' && payee.trim() && save()} />
        </Field>
        <div className="small muted">{t('Merchants')}: {keys.join(', ')}</div>
        <label className="check"><input type="checkbox" checked={rule} onChange={(e) => setRule(e.target.checked)} />{t('Also rename future imports (creates a rule)')}</label>
      </div>
    </Dialog>
  )
}

function TagManager() {
  const { version, bump } = useApp()
  const toast = useToast()
  const tags = useData(() => api.get('/tags'), [version])
  const [name, setName] = useState('')
  const [renaming, setRenaming] = useState(null)
  const [merging, setMerging] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const run = async (fn, msg) => {
    try { await fn(); if (msg) toast(msg); tags.reload(); bump() } catch (e) { toast(e.message, 'error') }
  }
  if (!tags.data) return <Loading rows={4} />
  const list = tags.data
  return (
    <section className="card">
      <div className="card-head">
        <div><h2>{t('Tags')}</h2><div className="sub">{t('Labels that cut across categories, like a trip or a renovation. Add them from a transaction, the bulk bar or a rule.')}</div></div>
      </div>
      <form className="row wrap tag-new" onSubmit={(e) => { e.preventDefault(); name.trim() && run(() => api.post('/tags', { name }), t('Tag created')).then(() => setName('')) }}>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t('New tag, e.g. vacation 2026')} maxLength={80} aria-label={t('New tag')} />
        <button className="btn" disabled={!name.trim()}>{t('Create tag')}</button>
      </form>
      {list.length === 0 ? (
        <Empty icon={TagsIcon} title={t('No tags yet')}>{t('Tags show up here once you add one to a transaction.')}</Empty>
      ) : (
        <div className="list">
          {list.map((tg) => (
            <div className="list-row" key={tg.id}>
              <TagPill name={tg.name} />
              <div className="grow meta">{tg.count === 1 ? t('{n} transaction', { n: 1 }) : t('{n} transactions', { n: tg.count })}</div>
              <Link className="small" to={`/transactions${qs({ tag: tg.id })}`}>{t('See transactions')}</Link>
              <div className="actions">
                <button className="icon-btn" onClick={() => setRenaming(tg)} aria-label={t('Rename {name}', { name: tg.name })}><Pencil /></button>
                {list.length > 1 && <button className="icon-btn" onClick={() => setMerging(tg)} aria-label={t('Merge {name} into another tag', { name: tg.name })}><Combine /></button>}
                <button className="icon-btn" onClick={() => setConfirm({ title: t('Delete the tag “{name}”?', { name: tg.name }), body: t('It comes off {n} transactions. The transactions stay.', { n: tg.count }), action: t('Delete'),
                  onConfirm: () => run(() => api.del(`/tags/${tg.id}`), t('Tag deleted')) })} aria-label={t('Delete {name}', { name: tg.name })}><Trash2 /></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {renaming && <TagRename tag={renaming} onClose={() => setRenaming(null)} onSave={(n) => run(() => api.patch(`/tags/${renaming.id}`, { name: n }), t('Tag renamed'))} />}
      {merging && <TagMerge tag={merging} tags={list} onClose={() => setMerging(null)}
        onSave={(target) => run(() => api.post('/tags/merge', { source_ids: [merging.id], target_id: target }), t('Tags merged'))} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </section>
  )
}

function TagRename({ tag, onClose, onSave }) {
  const [name, setName] = useState(tag.name)
  const save = async () => { await onSave(name); onClose() }
  return (
    <Dialog title={t('Rename tag')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={!name.trim()} onClick={save}>{t('Save')}</button></>}>
      <Field label={t('Name')}><input className="input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && name.trim() && save()} /></Field>
    </Dialog>
  )
}

function TagMerge({ tag, tags, onClose, onSave }) {
  const others = tags.filter((x) => x.id !== tag.id)
  const [target, setTarget] = useState(others[0]?.id)
  const save = async () => { await onSave(Number(target)); onClose() }
  return (
    <Dialog title={t('Merge “{name}”', { name: tag.name })} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" disabled={!target} onClick={save}>{t('Merge')}</button></>}>
      <Field label={t('Into')} hint={t('Its transactions and rules move to this tag, then “{name}” is removed.', { name: tag.name })}>
        <select className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
          {others.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </Field>
    </Dialog>
  )
}
