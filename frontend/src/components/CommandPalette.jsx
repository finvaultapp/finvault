import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeftRight, CornerDownLeft } from 'lucide-react'
import { api, qs } from '../api'
import { NAV } from './Layout'
import { useModal } from './ui'
import { money, date } from '../lib/format'
import { t } from '../i18n'

// Search pages and transactions. The text box is a combobox: arrow keys move through the results, Enter opens one.
export default function CommandPalette({ onClose, aiOn }) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const [txs, setTxs] = useState([])
  const navigate = useNavigate()
  const ref = useRef(null)
  const input = useRef(null)
  const id = useId()
  useModal(ref, onClose, () => input.current)

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
  const groups = [...new Set(results.map((r) => r.group))]

  useEffect(() => setActive(0), [q])
  useEffect(() => { document.getElementById(`${id}-${active}`)?.scrollIntoView({ block: 'nearest' }) }, [active, id])

  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Home' && results.length) { e.preventDefault(); setActive(0) }
    else if (e.key === 'End' && results.length) { e.preventDefault(); setActive(results.length - 1) }
    else if (e.key === 'Enter' && results[active]) { e.preventDefault(); results[active].go(); onClose() }
  }

  const count = results.length === 0 ? t('Nothing matches “{q}”.', { q }) : results.length === 1 ? t('1 result') : t('{n} results', { n: results.length })
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog palette" role="dialog" aria-modal="true" aria-label={t('Search')} ref={ref}>
        <input ref={input} className="input palette-input" placeholder={t('Search pages and transactions…')} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
          role="combobox" aria-expanded={results.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list" aria-label={t('Search pages and transactions')}
          aria-activedescendant={results[active] ? `${id}-${active}` : undefined} />
        <div className="palette-list" id={`${id}-list`} role="listbox" aria-label={t('Results')}>
          {groups.map((g, gi) => (
            <div key={g} role="group" aria-labelledby={`${id}-g${gi}`}>
              <div className="palette-group" id={`${id}-g${gi}`} role="presentation">{g}</div>
              {results.map((r, i) => {
                if (r.group !== g) return null
                const Icon = r.icon
                return (
                  <div key={r.key} id={`${id}-${i}`} role="option" aria-selected={i === active} className={`palette-item ${i === active ? 'on' : ''}`}
                    onMouseEnter={() => setActive(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => { r.go(); onClose() }}>
                    {Icon && <Icon />}<span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
                    {r.hint && <span className="small muted">{r.hint}</span>}
                    {i === active && <CornerDownLeft />}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
        {results.length === 0 && <div className="palette-group">{count}</div>}
        <div className="sr" role="status" aria-live="polite">{q ? count : ''}</div>
      </div>
    </div>
  )
}
