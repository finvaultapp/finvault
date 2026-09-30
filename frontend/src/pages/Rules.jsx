import { useState } from 'react'
import { Pencil, Play, Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { CategoryTile, Confirm, Empty, Loading, PageHead, Switch, useData, useToast } from '../components/ui'
import RuleDialog from '../components/RuleDialog'
import { t } from '../i18n'

const MATCH = { contains: 'contains', starts_with: 'starts with', equals: 'is', regex: 'matches', merchant: 'is the same merchant as' }

export default function Rules() {
  const { version, bump } = useApp()
  const toast = useToast()
  const rules = useData(() => api.get('/rules'), [version])
  const cats = useData(() => api.get('/categories'), [version])
  const accounts = useData(() => api.get('/accounts'), [])
  const tags = useData(() => api.get('/tags'), [version])
  const [editing, setEditing] = useState(null)
  const [confirm, setConfirm] = useState(null)

  if (!rules.data || !cats.data) return <Loading />
  const catById = Object.fromEntries(cats.data.map((c) => [c.id, c]))
  const tagById = Object.fromEntries((tags.data ?? []).map((x) => [x.id, x.name]))

  const runAll = async () => {
    const r = await api.post('/rules/apply', { only_uncategorized: true })
    toast(r.changed ? t(r.changed === 1 ? 'Categorized {n} transaction' : 'Categorized {n} transactions', { n: r.changed }) : t('No uncategorized transactions matched'))
    bump()
  }
  const toggle = async (r, is_active) => { await api.patch(`/rules/${r.id}`, { ...r, is_active }); rules.reload() }

  return (
    <>
      <PageHead title={t('Rules')} sub={t("Rules categorize repeat purchases automatically every time you import. Merchants you've categorized before are also remembered.")}>
        <button className="btn" onClick={runAll} disabled={!rules.data.length}><Play />{t('Run on uncategorized')}</button>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('New rule')}</button>
      </PageHead>
      <section className="card">
        {rules.data.length === 0 ? (
          <Empty icon={SlidersHorizontal} title={t('No rules yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('New rule')}</button>}>
            {t('Tip: categorize a transaction in the list and FinVault offers to turn it into a rule.')}
          </Empty>
        ) : (
          <div className="list">
            {rules.data.map((r) => {
              const c = catById[r.set_category_id]
              return (
                <div className="list-row" key={r.id} style={{ opacity: r.is_active ? 1 : 0.55 }}>
                  <CategoryTile name={c?.name} color={c?.color} />
                  <div className="grow">
                    <div className="title">
                      {r.match_field === 'payee' ? t('Payee') : t('Description')} {t(MATCH[r.match_type])} “{r.pattern}”
                    </div>
                    <div className="meta">
                      → {c ? c.name : t('category unchanged')}{r.set_payee ? ' · ' + t('rename to “{payee}”', { payee: r.set_payee }) : ''}{r.set_tag_id && tagById[r.set_tag_id] ? ' · ' + t('tag “{tag}”', { tag: tagById[r.set_tag_id] }) : ''}
                      {(r.amount_min != null || r.amount_max != null) ? ' · ' + t('amount {min} to {max}', { min: r.amount_min ?? '…', max: r.amount_max ?? '…' }) : ''} · {t('priority {n}', { n: r.priority })}
                    </div>
                  </div>
                  <Switch checked={r.is_active} onChange={(v) => toggle(r, v)} label={t('Active: {name}', { name: r.pattern })} />
                  <div className="actions">
                    <button className="icon-btn" onClick={() => setEditing(r)} aria-label={t('Edit {name}', { name: r.pattern })}><Pencil /></button>
                    <button className="icon-btn" onClick={() => setConfirm({ title: t('Delete this rule?'), body: t('Transactions it already categorized keep their category.'),
                      onConfirm: async () => { await api.del(`/rules/${r.id}`); rules.reload() } })} aria-label={t('Delete {name}', { name: r.pattern })}><Trash2 /></button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
      {editing && <RuleDialog rule={editing.id ? editing : null} categories={cats.data} accounts={accounts.data?.items ?? []}
        onClose={() => setEditing(null)} onSaved={(r) => { rules.reload(); bump(); if (r.applied) toast(t(r.applied === 1 ? 'Applied to {n} transaction' : 'Applied to {n} transactions', { n: r.applied })) }} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}
