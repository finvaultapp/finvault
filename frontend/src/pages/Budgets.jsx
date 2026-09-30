import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, PiggyBank, Plus, Repeat, Trash2 } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { CategoryTile, Dialog, Empty, Field, Loading, Money, PageHead, Progress, useData, useToast, Warnings } from '../components/ui'
import { addMonths, monthLabel, todayISO } from '../lib/format'
import { t } from '../i18n'

const thisMonth = () => todayISO().slice(0, 7)
const ROLLOVER = () => ({
  off: t('Off: every month starts fresh'),
  carry: t('Carry leftovers'),
  carry_all: t('Carry leftovers and overspending'),
})

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
  const available = b.total_available ?? b.total_budget
  const totalPct = available > 0 ? (b.total_spent / available) * 100 : b.total_spent > 0 ? 100 : 0
  const anyRollover = b.items.some((i) => i.rollover && i.rollover !== 'off')

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
              {anyRollover && <div className="figure"><div className="label muted small">{t('Carried in')}</div><div className="value"><Money value={b.total_carried} currency={c} sign /></div></div>}
              {anyRollover && <div className="figure"><div className="label muted small">{t('Available')}</div><div className="value"><Money value={available} currency={c} /></div></div>}
              <div className="figure"><div className="label muted small">{t('Left')}</div><div className={`value ${available - b.total_spent < 0 ? 'expense' : 'income'}`}><Money value={available - b.total_spent} currency={c} /></div></div>
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
                const rolls = i.rollover && i.rollover !== 'off'
                return (
                  <div className="cat-row" key={i.id}>
                    <CategoryTile name={i.name} color={i.color} />
                    <div className="grow">
                      <div className="line">
                        <Link className="name" style={{ color: 'inherit' }} to={`/transactions?category=${i.category_id}&month=${month}`}>{i.name}</Link>
                        <span className="small"><Money value={i.spent} currency={c} className="strong" /> <span className="muted">{t('of')}</span> <button className="link-btn" onClick={() => setEditing(i)}><span className="sr">{t('Change the budget for {name}:', { name: i.name })} </span><Money value={rolls ? i.available : i.budget} currency={c} /></button></span>
                        {i.percent > 100 ? <span className="pill red">{t('Over by')} <Money value={-i.remaining} currency={c} /></span>
                          : i.percent > pace + 10 ? <span className="pill amber">{t('Ahead of pace')}</span> : <span className="pill green"><Money value={i.remaining} currency={c} /> {t('left')}</span>}
                      </div>
                      <div className="budget-line"><Progress value={i.percent} color={tone} /><span className="small muted num" style={{ width: 40, textAlign: 'right' }}>{Math.round(i.percent ?? 0)}%</span></div>
                      {rolls && (
                        <div className="rollover-figs small" aria-label={t('Rollover for {name}', { name: i.name })}>
                          <span title={ROLLOVER()[i.rollover]}><Repeat size={13} aria-hidden="true" /> {t('Limit')} <Money value={i.budget} currency={c} /></span>
                          <span>{t('Carried in')} <Money value={i.carried} currency={c} sign className={i.carried < 0 ? 'expense' : ''} /></span>
                          <span>{t('Available')} <Money value={i.available} currency={c} className="strong" /></span>
                          <span>{t('Spent')} <Money value={i.spent} currency={c} /></span>
                          <span>{t('Left')} <Money value={i.remaining} currency={c} className={i.remaining < 0 ? 'expense strong' : 'strong'} /></span>
                        </div>
                      )}
                    </div>
                    <div className="actions"><button className="icon-btn" aria-label={t('Remove the budget for {name}', { name: i.name })} onClick={async () => { await api.del(`/budgets/${i.id}`); bump() }}><Trash2 /></button></div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
      {editing && <BudgetDialog item={editing} month={month} cats={cats.data.filter((x) => x.kind === 'expense')} currency={c} onClose={() => setEditing(null)} onSaved={bump} />}
    </>
  )
}

function BudgetDialog({ item, month, cats, currency, onClose, onSaved }) {
  const toast = useToast()
  const [category_id, setCat] = useState(item.category_id ?? cats[0]?.id)
  const [amount, setAmount] = useState(item.budget ?? '')
  const [rollover, setRollover] = useState(item.rollover ?? 'off')
  const [start, setStart] = useState(item.rollover_start ?? month)
  const modes = ROLLOVER()
  const save = async () => {
    try {
      await api.put('/budgets', { category_id: Number(category_id), amount: Number(amount) })
      if (rollover !== (item.rollover ?? 'off') || (rollover !== 'off' && start !== item.rollover_start)) {
        const id = item.id ?? (await api.get(`/budgets${qs({ month })}`)).items.find((x) => x.category_id === Number(category_id))?.id
        if (id) await api.put(`/budgets/${id}/rollover`, { mode: rollover, start: rollover === 'off' ? null : start || null })
      }
      onSaved(); onClose()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={item.id ? t('Budget for {name}', { name: item.name }) : t('Set a budget')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={amount === ''}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Category')}><select className="input" value={category_id} onChange={(e) => setCat(e.target.value)} disabled={!!item.id}>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label={t('Monthly limit ({currency})', { currency })}><input className="input" type="number" min="0" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus /></Field>
        <Field label={t('Rollover')} className="full" hint={rollover === 'carry' ? t('Money you don’t spend adds to next month. An overspent month carries nothing.')
          : rollover === 'carry_all' ? t('Money you don’t spend adds to next month, and overspending comes out of next month.') : t('Each month gets exactly its limit.')}>
          <select className="input" value={rollover} onChange={(e) => setRollover(e.target.value)}>
            {Object.entries(modes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        {rollover !== 'off' && (
          <Field label={t('Start carrying from')} className="full" hint={t('Months before this are ignored. At most 24 months of history are counted.')}>
            <input className="input" type="month" value={start ?? ''} onChange={(e) => setStart(e.target.value)} />
          </Field>
        )}
      </div>
    </Dialog>
  )
}
