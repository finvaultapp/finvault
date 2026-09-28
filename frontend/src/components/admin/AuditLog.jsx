import { useState } from 'react'
import { ChevronLeft, ChevronRight, FileDown } from 'lucide-react'
import { api, qs } from '../../api'
import { useData } from '../ui'
import { t } from '../../i18n'
import { dateTime } from './Backups'

const GROUPS = [['auth', 'Sign-in and security'], ['admin', 'Admin actions'], ['backup', 'Backups'], ['sync', 'Bank sync'], ['ai', 'AI keys']]
const PAGE_SIZE = 25

function details(d) {
  return Object.entries(d || {})
    .filter(([, v]) => v !== null && v !== '' && v !== undefined)
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : String(v)}`)
    .join(' · ')
}

export default function AuditLog({ users = [] }) {
  const [event, setEvent] = useState('')
  const [member, setMember] = useState('')
  const [page, setPage] = useState(1)
  const types = useData(() => api.get('/admin/audit/events'), [])
  const params = { event, user_id: member, page_size: PAGE_SIZE }
  const log = useData(() => api.get(`/admin/audit${qs({ ...params, page })}`), [event, member, page])
  const data = log.data
  const filter = (fn) => (e) => { fn(e.target.value); setPage(1) }

  return (
    <section className="card audit">
      <div className="card-head">
        <div><h2>{t('Audit log')}</h2><div className="sub">{t('Sign-ins, security changes and admin actions. Passwords and secret values are never recorded. Kept for 365 days.')}</div></div>
        <a className="btn sm" href={`/api/admin/audit.csv${qs({ event, user_id: member })}`} download><FileDown />{t('Export CSV')}</a>
      </div>
      <div className="card-body audit-filters">
        <label className="field"><span>{t('Event')}</span>
          <select className="input sm" value={event} onChange={filter(setEvent)}>
            <option value="">{t('All events')}</option>
            {GROUPS.map(([id, label]) => <option key={id} value={id}>{t(label)}</option>)}
            <option disabled>──────────</option>
            {types.data?.map((e) => <option key={e.id} value={e.id}>{t(e.label)}</option>)}
          </select>
        </label>
        <label className="field"><span>{t('Member')}</span>
          <select className="input sm" value={member} onChange={filter(setMember)}>
            <option value="">{t('Everyone')}</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
          </select>
        </label>
      </div>
      {data && data.items.length === 0 ? <div className="card-body small muted" style={{ borderTop: '1px solid var(--rule)' }}>{t('No events match.')}</div> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>{t('When')}</th><th>{t('Event')}</th><th>{t('Member')}</th><th className="hide-sm">{t('IP address')}</th><th className="hide-sm">{t('Details')}</th></tr></thead>
          <tbody>{data?.items.map((e) => (
            <tr key={e.id}>
              <td className="small" style={{ whiteSpace: 'nowrap' }}>{dateTime(e.created_at)}</td>
              <td><span className={`pill ${/failed/.test(e.event) ? 'red' : ''}`}>{t(e.label)}</span></td>
              <td className="small">
                <div>{e.email || <span className="muted">{t('System')}</span>}</div>
                {e.target_email && e.target_email !== e.email && <div className="muted">→ {e.target_email}</div>}
              </td>
              <td className="hide-sm small muted"><code>{e.ip}</code></td>
              <td className="hide-sm small muted audit-detail">{details(e.detail)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      {data && data.pages > 1 && (
        <div className="audit-pager">
          <button className="btn sm ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft />{t('Previous')}</button>
          <span className="small muted">{t('Page {page} of {pages}', { page: data.page, pages: data.pages })} · {t('{n} events', { n: data.total })}</span>
          <button className="btn sm ghost" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>{t('Next')}<ChevronRight /></button>
        </div>
      )}
    </section>
  )
}
