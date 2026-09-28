import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, PiggyBank, Plus, Trash2 } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { CategoryTile, Dialog, Empty, Field, Loading, Money, PageHead, Progress, useData, useToast, Warnings } from '../components/ui'
import { addMonths, monthLabel, todayISO } from '../lib/format'
import { t } from '../i18n'

const thisMonth = () => todayISO().slice(0, 7)

export default function Budgets() {
  const { version, bump } = useApp()
  const [month, setMonth] = useState(thisMonth)
  const budgets = useData(() => api.get(`/budgets${qs({ month })}`), [month, version])
  const cats = useData(() => api.get('/categories'), [version])
  const [editing, setEditing] = useState(null)
  if (!budgets.data || !cats.data) return <Loading />
  const b = budgets.data
  const c = b.currency
  const pace = b.month_progress * 100
  const totalPct = b.total_budget ? (b.total_spent / b.total_budget) * 100 : 0

  return (
    <>
      <PageHead title={t('Budgets')} sub={t('Monthly limits per spending category, in your main currency.')}>
        <button className="icon-btn bordered" onClick={() => setMonth(addMonths(month, -1))} aria-label={t('Previous month')}><ChevronLeft /></button>
        <span className="btn" style={{ pointerEvents: 'none' }}>{monthLabel(month)}</span>
        <button className="icon-btn bordered" onClick={() => setMonth(addMonths(month, 1))} aria-label={t('Next month')}><ChevronRight /></button>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Set a budget')}</button>
      </PageHead>
      <div className="stack">
        <Warnings items={b.warnings} />
        {b.items.length > 0 && (
          <section className="card card-body">
            <div className="row wrap" style={{ gap: 28, marginBottom: 14 }}>
              <div className="figure"><div className="label muted small">{t('Spent')}</div><div className="value"><Money value={b.total_spent} currency={c} /></div></div>
              <div className="figure"><div className="label muted small">{t('Budgeted')}</div><div className="value"><Money value={b.total_budget} currency={c} /></div></div>
              <div className="figure"><div className="label muted small">{t('Left')}</div><div className={`value ${b.total_budget - b.total_spent < 0 ? 'expense' : 'income'}`}><Money value={b.total_budget - b.total_spent} currency={c} /></div></div>
            </div>
            <div style={{ position: 'relative' }}>
              <Progress thick value={totalPct} color={totalPct > pace + 10 ? 'var(--warn-strong)' : 'var(--primary)'} />
              {b.month_progress > 0 && b.month_progress < 1 && <span title={t('Today')} style={{ position: 'absolute', top: -4, left: `${pace}%`, width: 2, height: 16, background: 'var(--fg)', borderRadius: 1 }} />}
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>{b.month_progress < 1 && b.month_progress > 0 ? t('{pct}% of the month has passed; the line marks today.', { pct: Math.round(pace) }) : ''}</p>
          </section>
        )}
        <section className="card">
          {b.items.length === 0 ? (
            <Empty icon={PiggyBank} title={t('No budgets yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Set your first budget')}</button>}>
              {t('Start with the categories you want to keep an eye on, like groceries and dining out.')}
            </Empty>
          ) : (
            <div className="list">
              {b.items.map((i) => {
                const tone = i.percent > 100 ? 'var(--expense)' : i.percent > pace + 10 ? 'var(--warn-strong)' : 'var(--income)'
                return (
                  <div className="cat-row" key={i.id}>
                    <CategoryTile name={i.name} color={i.color} />
                    <div className="grow">
                      <div className="line">
                        <Link className="name" style={{ color: 'inherit' }} to={`/transactions?category=${i.category_id}&month=${month}`}>{i.name}</Link>
                        <span className="small"><Money value={i.spent} currency={c} className="strong" /> <span className="muted">{t('of')}</span> <button className="link-btn" onClick={() => setEditing(i)}><Money value={i.budget} currency={c} /></button></span>
                        {i.percent > 100 ? <span className="pill red">{t('Over by')} <Money value={-i.remaining} currency={c} /></span>
                          : i.percent > pace + 10 ? <span className="pill amber">{t('Ahead of pace')}</span> : <span className="pill green"><Money value={i.remaining} currency={c} /> {t('left')}</span>}
                      </div>
                      <div className="budget-line"><Progress value={i.percent} color={tone} /><span className="small muted num" style={{ width: 40, textAlign: 'right' }}>{Math.round(i.percent ?? 0)}%</span></div>
                    </div>
                    <div className="actions"><button className="icon-btn" aria-label={t('Remove budget')} onClick={async () => { await api.del(`/budgets/${i.id}`); bump() }}><Trash2 /></button></div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
      {editing && <BudgetDialog item={editing} cats={cats.data.filter((x) => x.kind === 'expense')} currency={c} onClose={() => setEditing(null)} onSaved={bump} />}
    </>
  )
}

function BudgetDialog({ item, cats, currency, onClose, onSaved }) {
  const toast = useToast()
  const [category_id, setCat] = useState(item.category_id ?? cats[0]?.id)
  const [amount, setAmount] = useState(item.budget ?? '')
  const save = async () => {
    try { await api.put('/budgets', { category_id: Number(category_id), amount: Number(amount) }); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={item.id ? t('Budget for {name}', { name: item.name }) : t('Set a budget')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={amount === ''}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Category')}><select className="input" value={category_id} onChange={(e) => setCat(e.target.value)} disabled={!!item.id}>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label={t('Monthly limit ({currency})', { currency })}><input className="input" type="number" min="0" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus /></Field>
      </div>
    </Dialog>
  )
}
