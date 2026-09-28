import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeftRight, CornerDownLeft } from 'lucide-react'
import { api, qs } from '../api'
import { NAV } from './Layout'
import { money, date } from '../lib/format'
import { t } from '../i18n'

export default function CommandPalette({ onClose, aiOn }) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const [txs, setTxs] = useState([])
  const navigate = useNavigate()

  const pages = useMemo(() => NAV.flatMap((g) => g.items).filter((i) => !i.needsAi || aiOn)
    .concat([{ to: '/settings', label: 'Settings' }, { to: '/import', label: 'Import a statement' }]), [aiOn])

  useEffect(() => {
    if (q.trim().length < 2) { setTxs([]); return }
    const timer = setTimeout(() => api.get(`/transactions${qs({ q, page_size: 6 })}`).then((r) => setTxs(r.items)).catch(() => {}), 180)
    return () => clearTimeout(timer)
  }, [q])

  const matches = pages.filter((p) => t(p.label).toLowerCase().includes(q.toLowerCase()))
  const results = [
    ...matches.map((p) => ({ key: `p${p.to}${p.label}`, group: t('Go to'), label: t(p.label), icon: p.icon, go: () => navigate(p.to) })),
    ...txs.map((tx) => ({ key: `t${tx.id}`, group: t('Transactions'), label: tx.description, hint: `${date(tx.date)} · ${money(tx.amount, tx.currency)}`,
      icon: ArrowLeftRight, go: () => navigate(`/transactions?q=${encodeURIComponent(q)}`) })),
  ]

  useEffect(() => setActive(0), [q])
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
      if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
      if (e.key === 'Enter' && results[active]) { results[active].go(); onClose() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  let lastGroup = null
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog palette" role="dialog" aria-label={t('Search')}>
        <input autoFocus className="input palette-input" placeholder={t('Search pages and transactions…')} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="palette-list" role="listbox">
          {results.length === 0 && <div className="palette-group">{t('Nothing matches “{q}”.', { q })}</div>}
          {results.map((r, i) => {
            const header = r.group !== lastGroup ? <div className="palette-group">{r.group}</div> : null
            lastGroup = r.group
            const Icon = r.icon
            return (
              <div key={r.key}>
                {header}
                <button className={`palette-item ${i === active ? 'on' : ''}`} onMouseEnter={() => setActive(i)} onClick={() => { r.go(); onClose() }}>
                  {Icon && <Icon />}<span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
                  {r.hint && <span className="small muted">{r.hint}</span>}
                  {i === active && <CornerDownLeft />}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
