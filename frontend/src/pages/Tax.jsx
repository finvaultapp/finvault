import { useState } from 'react'
import { Download, FileText, Info } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { CategoryTile, Empty, Loading, Money, PageHead, useData, useToast, Warnings } from '../components/ui'
import { date } from '../lib/format'
import { TAX_TAGS } from '../lib/tax'


export default function Tax() {
  const { version, bump } = useApp()
  const toast = useToast()
  const thisYear = new Date().getFullYear()
  const [year, setYear] = useState(new Date().getMonth() < 4 ? thisYear - 1 : thisYear)
  const summary = useData(() => api.get(`/tax/summary${qs({ year })}`), [year, version])
  const cats = useData(() => api.get('/categories'), [version])
  const [open, setOpen] = useState(null)
  const tags = TAX_TAGS()

  if (!summary.data || !cats.data) return <Loading />
  const s = summary.data
  const tagCategory = async (c, tax_tag) => {
    try { await api.put(`/categories/${c.id}/tax-tag`, { tax_tag: tax_tag || null }); bump() } catch (e) { toast(e.message, 'error') }
  }

  return (
    <>
      <PageHead title={t('Tax time')} sub={t('Spending you may be able to claim, gathered in one place for your accountant.')}>
        <select className="input" style={{ width: 110 }} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label={t('Tax year')}>
          {Array.from({ length: 6 }, (_, i) => thisYear - i).map((y) => <option key={y}>{y}</option>)}
        </select>
        <a className="btn primary" href={`/api/tax/export?year=${year}`}><Download />{t('Export for my accountant')}</a>
      </PageHead>
      <div className="stack">
        <div className="banner info"><Info /><div className="banner-body">{t('FinVault doesn\'t decide what CRA accepts. Keep your receipts and confirm eligibility with your accountant or the CRA guides.')}</div></div>
        <Warnings items={s.warnings} />
        <div className="grid-2" style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)' }}>
          <section className="card">
            <div className="card-head"><h2>{t('{year} summary', { year })}</h2><strong><Money value={s.total} currency={s.currency} /></strong></div>
            {s.groups.length === 0 ? (
              <Empty icon={FileText} title={t('Nothing tagged for {year}', { year })}>{t('Tag categories on the right (for example Health as medical), or tag single transactions from the transaction editor.')}</Empty>
            ) : (
              <div className="list">
                {s.groups.map((g) => (
                  <div key={g.tag}>
                    <button className="cat-row" style={{ width: '100%', border: 0, background: 'none', font: 'inherit', cursor: 'pointer', textAlign: 'left' }} onClick={() => setOpen(open === g.tag ? null : g.tag)}>
                      <div className="grow"><div className="line"><span className="name">{tags[g.tag] ?? g.label}</span><Money value={g.total} currency={s.currency} className="strong" /></div>
                        <div className="small muted">{t(g.count === 1 ? '{n} transaction' : '{n} transactions', { n: g.count })}</div></div>
                    </button>
                    {open === g.tag && (
                      <div className="table-wrap" style={{ padding: '0 12px 12px' }}>
                        <table className="table"><tbody>
                          {g.items.map((i, n) => (
                            <tr key={n}><td className="num" style={{ whiteSpace: 'nowrap' }}>{date(i.date)}</td><td className="desc"><div>{i.description}</div><small>{i.account}{i.note ? ` · ${i.note}` : ''}</small></td><td className="amount"><Money value={i.amount} currency={s.currency} /></td></tr>
                          ))}
                        </tbody></table>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="card" style={{ alignSelf: 'start' }}>
            <div className="card-head"><div><h2>{t('Tag your categories')}</h2><div className="sub">{t('Everything in a tagged category counts. Single transactions can override it.')}</div></div></div>
            <div className="list">
              {cats.data.filter((c) => c.kind === 'expense').map((c) => (
                <div className="list-row" key={c.id} style={{ padding: '9px 18px' }}>
                  <CategoryTile size="sm" name={c.name} color={c.color} />
                  <span className="grow title">{c.name}</span>
                  <select className="input sm" style={{ width: 190 }} value={c.tax_tag ?? ''} onChange={(e) => tagCategory(c, e.target.value)} aria-label={t('Tax tag for {name}', { name: c.name })}>
                    <option value="">{t('Not tagged')}</option>
                    {Object.entries(tags).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
