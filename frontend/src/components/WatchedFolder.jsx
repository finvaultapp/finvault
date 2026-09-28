import { FolderInput, RefreshCw } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Switch, useData, useToast } from './ui'

// Import page card: which accounts pick up files from the watched folder, and where to put them.
export default function WatchedFolder() {
  const { version, bump } = useApp()
  const toast = useToast()
  const inbox = useData(() => api.get('/inbox'), [version])
  if (!inbox.data) return null
  const { enabled, root, accounts } = inbox.data
  const toggle = async (a, watch) => {
    try { await api.put(`/inbox/accounts/${a.id}`, { watch }); inbox.reload() } catch (e) { toast(e.message, 'error') }
  }
  const scan = async () => {
    try { const r = await api.post('/inbox/scan'); toast(r.imported ? t('Imported {n} transactions from the folder', { n: r.imported }) : t('No new files in the folder')); bump() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <section className="card" style={{ marginTop: 20 }}>
      <div className="card-head">
        <div><h2 className="row" style={{ gap: 8 }}><FolderInput size={17} />{t('Watched folder')}</h2>
          <div className="sub">{t('Save bank exports into a folder (for example on your NAS) and FinVault imports them every couple of minutes.')}</div></div>
        {enabled && <button className="btn sm" onClick={scan}><RefreshCw />{t('Check now')}</button>}
      </div>
      {!enabled ? (
        <div className="list-row muted small">{t('Turned off. An admin can enable it in Admin → Optional features.')}</div>
      ) : (
        <div className="list">
          {accounts.map((a) => (
            <div className="list-row" key={a.id} style={{ flexWrap: 'wrap' }}>
              <Switch checked={a.watch} onChange={(v) => toggle(a, v)} label={t('Watch folder for {name}', { name: a.name })} />
              <div className="grow" style={{ minWidth: 200 }}>
                <div className="title">{a.name}</div>
                {a.watch && <div className="meta" style={{ wordBreak: 'break-all' }}><code>{root}/{a.folder}/</code></div>}
              </div>
            </div>
          ))}
          <div className="list-row small muted">{t('Imported files move to an "imported" subfolder. Files that can\'t be read move to "failed" with a note explaining why.')}</div>
        </div>
      )}
    </section>
  )
}
