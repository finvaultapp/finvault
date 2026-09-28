import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Cloud, Download, HardDrive, Loader2, Save } from 'lucide-react'
import { api } from '../../api'
import { Field, Switch, useData, useToast } from '../ui'
import { currentLocale } from '../../lib/format'
import { t } from '../../i18n'
import { serverText } from '../../lib/serverText'

export function dateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(currentLocale(), { dateStyle: 'medium', timeStyle: 'short' })
}

function size(bytes) {
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes || 0
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toLocaleString(currentLocale(), { maximumFractionDigits: i ? 1 : 0 })} ${units[i]}`
}

export default function Backups() {
  const toast = useToast()
  const b = useData(() => api.get('/admin/backups'), [])
  const [pass, setPass] = useState('')
  const [keep, setKeep] = useState(null)
  const s = b.data

  // While a backup runs, check back every two seconds.
  useEffect(() => {
    if (!s?.running) return undefined
    const id = setTimeout(b.reload, 2000)
    return () => clearTimeout(id)
  }, [s])

  const patch = async (body, done) => {
    try { await api.patch('/admin/backups', body); b.reload(); toast(done || t('Settings saved')); return true } catch (e) { toast(e.message, 'error'); return false }
  }
  const runNow = async () => {
    try { await api.post('/admin/backups/run'); toast(t('Backup started')); setTimeout(b.reload, 400) } catch (e) { toast(e.message, 'error') }
  }

  if (!s) return <section className="card"><div className="card-head"><h2>{t('Encrypted backups')}</h2></div><div className="card-body muted small">{b.error ? b.error.message : t('Loading…')}</div></section>
  const last = s.last_run
  const keepValue = keep ?? s.keep

  return (
    <section className="card backups">
      <div className="card-head">
        <div><h2>{t('Encrypted backups')}</h2><div className="sub">{t('Nightly copies of the database, receipts and secret key, locked with your passphrase. Off by default.')}</div></div>
        <button className="btn sm" onClick={runNow} disabled={!s.passphrase_set || s.running}>
          {s.running ? <Loader2 className="spin" /> : <Save />}{s.running ? t('Backing up…') : t('Back up now')}
        </button>
      </div>
      <div className="list">
        <div className="list-row">
          <div className="grow">
            <div className="strong">{t('Nightly backup')}</div>
            <div className="small muted">{s.passphrase_set ? t('Runs once a day after {hour}:00 (server time).', { hour: s.hour }) : t('Set a passphrase first.')}</div>
          </div>
          <Switch checked={s.enabled} label={t('Nightly backup')} onChange={(v) => { if (v && !s.passphrase_set) { toast(t('Set a passphrase first.'), 'error'); return } patch({ enabled: v }) }} />
        </div>
      </div>
      <div className="card-body stack" style={{ gap: 14, borderTop: '1px solid var(--rule)' }}>
        <div className="form-grid">
          <Field label={t('Backup passphrase')} hint={s.passphrase_set ? t('A passphrase is saved. Type a new one to replace it.') : t('At least 12 characters.')}>
            <input className="input" type="password" autoComplete="new-password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder={s.passphrase_set ? '••••••••••••' : ''} />
          </Field>
          <Field label={t('Backups to keep')} hint={t('Older ones are deleted after each backup.')}>
            <input className="input" type="number" min="1" max="365" value={keepValue} onChange={(e) => setKeep(Number(e.target.value))} />
          </Field>
        </div>
        <div className="banner warn"><AlertTriangle /><div className="banner-body">{t("Write the passphrase down somewhere safe. Without it, nobody can open these backups, and FinVault can't recover it.")}</div></div>
        <div className="row">
          <button className="btn primary" disabled={(pass && pass.length < 12) || (!pass && keepValue === s.keep)}
            onClick={async () => { const body = {}; if (pass) body.passphrase = pass; if (keepValue !== s.keep) body.keep = keepValue; if (await patch(body)) { setPass(''); setKeep(null) } }}>
            {t('Save backup settings')}
          </button>
        </div>
      </div>

      <div className="card-body stack" style={{ gap: 10, borderTop: '1px solid var(--rule)' }}>
        <h3>{t('Destinations')}</h3>
        <div className="backup-dest">
          <HardDrive />
          <div className="grow"><div className="strong">{t('Folder on this server')}</div><code className="small">{s.local.path}</code></div>
          {s.local.ok ? <span className="pill green">{t('Writable')}</span> : <span className="pill red" title={serverText(s.local.error)}>{t('Not writable')}</span>}
        </div>
        <div className="backup-dest">
          <Cloud />
          <div className="grow">
            <div className="strong">{t('S3-compatible storage')}</div>
            <div className="small muted">{s.s3.configured ? `${s.s3.endpoint} · ${s.s3.bucket}/${s.s3.prefix}` : t('Not set up. Add the BACKUP_S3_ settings to the server’s .env to also send a copy there.')}</div>
          </div>
          {s.s3.configured ? (last?.s3_status === 'failed' ? <span className="pill red">{t('Last upload failed')}</span> : <span className="pill green">{t('On')}</span>) : <span className="pill">{t('Off')}</span>}
        </div>
        {last && !s.running && (last.status === 'ok'
          ? <div className="banner info"><CheckCircle2 /><div className="banner-body">{t('Last backup: {date}', { date: dateTime(last.finished_at) })}</div></div>
          : <div className="banner warn"><AlertTriangle /><div className="banner-body"><strong>{t('The last backup failed.')}</strong> {serverText(last.error)}</div></div>)}
      </div>

      <div className="card-head" style={{ borderTop: '1px solid var(--rule)' }}><h3>{t('Saved backups')}</h3><span className="small muted">{t('Restore with backend/scripts/restore_backup.py (see README).')}</span></div>
      {s.backups.length === 0 ? <div className="card-body small muted">{t('No backups yet.')}</div> : (
        <div className="list">
          {s.backups.map((x) => (
            <div className="list-row" key={x.name}>
              <div className="grow"><div className="title">{dateTime(x.created_at)}</div><div className="meta"><code>{x.name}</code></div></div>
              <span className="small muted">{size(x.size)}</span>
              <a className="icon-btn" href={`/api/admin/backups/${encodeURIComponent(x.name)}/download`} download aria-label={t('Download')} title={t('Download')}><Download /></a>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
