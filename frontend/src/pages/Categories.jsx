import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { CategoryTile, Confirm, Dialog, Field, Loading, PageHead, useData, useToast } from '../components/ui'
import { t } from '../i18n'

const KINDS = { expense: 'Expenses', income: 'Income', transfer: 'Transfers (not counted as income or spending)' }
const SWATCHES = ['#6366F1', '#8B5CF6', '#EC4899', '#F43F5E', '#F97316', '#F59E0B', '#10B981', '#14B8A6', '#0EA5E9', '#3B82F6', '#64748B', '#A16207']

export default function Categories() {
  const { version, bump } = useApp()
  const cats = useData(() => api.get('/categories'), [version])
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!cats.data) return <Loading />

  return (
    <>
      <PageHead title={t('Categories')} sub={t("Transfers between your own accounts, like credit card payments, should use a transfer category so they don't count as spending.")}>
        <button className="btn primary" onClick={() => setEditing({ kind: 'expense', color: SWATCHES[0] })}><Plus />{t('New category')}</button>
      </PageHead>
      <div className="stack">
        {Object.entries(KINDS).map(([kind, label]) => {
          const items = cats.data.filter((c) => c.kind === kind)
          return (
            <section className="card" key={kind}>
              <div className="card-head"><h2>{t(label)}</h2><span className="muted small">{items.length}</span></div>
              <div className="list">
                {items.map((c) => (
                  <div className="list-row" key={c.id}>
                    <CategoryTile name={c.name} color={c.color} />
                    <div className="grow">
                      <div className="title">{c.name}</div>
                      <div className="meta">
                        {c.parent_id ? t('Inside {name}', { name: cats.data.find((p) => p.id === c.parent_id)?.name }) + ' · ' : ''}
                        <Link to={`/transactions?category=${c.id}`}>{t(c.transaction_count === 1 ? '{n} transaction' : '{n} transactions', { n: c.transaction_count })}</Link>
                      </div>
                    </div>
                    <div className="actions">
                      <button className="icon-btn" onClick={() => setEditing(c)} aria-label={t('Edit')}><Pencil /></button>
                      <button className="icon-btn" aria-label={t('Delete')} onClick={() => setConfirm({ title: t('Delete “{name}”?', { name: c.name }),
                        body: c.transaction_count ? t(c.transaction_count === 1 ? '{n} transaction will become uncategorized.' : '{n} transactions will become uncategorized.', { n: c.transaction_count }) : t('No transactions use it.'),
                        onConfirm: async () => { await api.del(`/categories/${c.id}`); bump() } })}><Trash2 /></button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )
        })}
      </div>
      {editing && <CategoryDialog cat={editing} all={cats.data} onClose={() => setEditing(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function CategoryDialog({ cat, all, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ name: cat.name ?? '', kind: cat.kind, color: cat.color, parent_id: cat.parent_id ?? null })
  const save = async () => {
    try {
      const body = { ...f, parent_id: f.parent_id ? Number(f.parent_id) : null }
      if (cat.id) await api.patch(`/categories/${cat.id}`, body)
      else await api.post('/categories', body)
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={cat.id ? t('Edit category') : t('New category')} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className="btn primary" onClick={save} disabled={!f.name}>{t('Save')}</button>
    </>}>
      <div className="stack" style={{ gap: 14 }}>
        <div className="row"><CategoryTile name={f.name} color={f.color} /><Field label={t('Name')} className="grow" ><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
        <Field label={t('Type')}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="expense">{t('Expense')}</option><option value="income">{t('Income')}</option><option value="transfer">{t('Transfer')}</option></select></Field>
        <Field label={t('Inside another category')} hint={t('Optional. Budgets on the parent include its sub-categories.')}>
          <select className="input" value={f.parent_id ?? ''} onChange={(e) => setF({ ...f, parent_id: e.target.value || null })}>
            <option value="">{t('None')}</option>{all.filter((c) => c.id !== cat.id && c.kind === f.kind && !c.parent_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></Field>
        <div className="field"><span>{t('Colour')}</span>
          <div className="row wrap" style={{ gap: 8 }}>
            {SWATCHES.map((s) => (
              <button key={s} type="button" aria-label={s} onClick={() => setF({ ...f, color: s })}
                style={{ width: 28, height: 28, borderRadius: 8, background: s, border: f.color === s ? '2px solid var(--fg)' : '2px solid transparent', cursor: 'pointer' }} />
            ))}
          </div>
        </div>
      </div>
    </Dialog>
  )
}
