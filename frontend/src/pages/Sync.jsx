import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Ban, Link2, Loader2, Plug, RefreshCw, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { api, qs } from '../api'
import { useApp } from '../context'
import { Confirm, Dialog, Empty, Field, Loading, PageHead, useData, useToast } from '../components/ui'
import { date } from '../lib/format'
import { t } from '../i18n'
import { serverText } from '../lib/serverText'

export default function Sync() {
  const { version, bump } = useApp()
  const toast = useToast()
  const status = useData(() => api.get('/sync/status'), [version])
  const accounts = useData(() => api.get('/accounts'), [version])
  const [connecting, setConnecting] = useState(null)
  const [linking, setLinking] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [syncing, setSyncing] = useState(null)

  // Returning from a GoCardless bank consent screen.
  useEffect(() => {
    const cid = sessionStorage.getItem('fv.gc.pending')
    if (cid && new URLSearchParams(location.search).get('ref')) {
      sessionStorage.removeItem('fv.gc.pending')
      setLinking(Number(cid))
    }
  }, [])

  if (!status.data) return <Loading />
  const s = status.data
  const available = s.providers.filter((p) => p.available)

  const syncNow = async (c) => {
    setSyncing(c.id)
    try { const r = await api.post(`/sync/connections/${c.id}/sync`); toast(t(r.imported === 1 ? 'Synced {n} new transaction' : 'Synced {n} new transactions', { n: r.imported })); bump() } catch (e) { toast(e.message, 'error') }
    setSyncing(null)
  }

  return (
    <>
      <PageHead title={t('Bank sync')} sub={t('Optional read-only connections for non-Canadian banks. Everything else comes in through file import.')}>
        {available.map((p) => <button key={p.id} className="btn" onClick={() => setConnecting(p.id)}><Plug />{t('Connect {name}', { name: p.name.split(' ')[0] })}</button>)}
      </PageHead>
      <div className="stack">
        <div className="banner ca">
          <Ban />
          <div className="banner-body"><strong>{t('Canadian banks are never connected.')}</strong> {t(s.canada)} <Link to="/import">{t('Go to import')}</Link></div>
        </div>
        {!s.enabled && <div className="card"><Empty icon={Plug} title={t('Bank sync is turned off')}>{t("An admin can enable it in Admin → Optional features, after adding provider credentials to the server's .env file.")}</Empty></div>}
        {s.enabled && (
          <section className="card">
            <div className="card-head"><h2>{t('Providers on this server')}</h2></div>
            <div className="list">
              {s.providers.map((p) => (
                <div className="list-row" key={p.id}>
                  <Plug className="row-icon" aria-hidden="true" />
                  <div className="grow"><div className="title">{p.name}</div><div className="meta">{t(p.region)} · {p.available ? t('ready') : t('needs {what}', { what: t(p.needs) })}</div></div>
                  {p.available ? <span className="pill green">{t('Available')}</span> : <span className="pill">{t('Not set up')}</span>}
                </div>
              ))}
            </div>
          </section>
        )}
        {s.connections.length > 0 && (
          <section className="card">
            <div className="card-head"><h2>{t('Your connections')}</h2></div>
            <div className="list">
              {s.connections.map((c) => (
                <div className="list-row" key={c.id}>
                  <Link2 className="row-icon" aria-hidden="true" />
                  <div className="grow">
                    <div className="row" style={{ gap: 8 }}><span className="title">{c.name}</span><span className={`pill ${c.status === 'active' ? 'green' : c.status === 'error' ? 'red' : 'amber'}`}>{t(c.status)}</span></div>
                    <div className="meta">{c.provider} · {c.accounts.length ? c.accounts.map((a) => a.name).join(', ') : t('no accounts linked')} · {c.last_synced_at ? t('synced {date}', { date: date(c.last_synced_at) }) : t('never synced')}</div>
                    {c.last_error && <div className="small expense">{serverText(c.last_error)}</div>}
                  </div>
                  <button className="btn sm" onClick={() => setLinking(c.id)}>{t('Link accounts')}</button>
                  <button className="btn sm" onClick={() => syncNow(c)} disabled={!c.accounts.length || syncing === c.id}>{syncing === c.id ? <Loader2 className="spin" /> : <RefreshCw />}{t('Sync')}</button>
                  <button className="icon-btn" aria-label={t('Disconnect')} onClick={() => setConfirm({ title: t('Disconnect {name}?', { name: c.name }), body: t('Stored provider credentials are deleted. Imported transactions stay.'), action: t('Disconnect'), onConfirm: async () => { await api.del(`/sync/connections/${c.id}`); bump() } })}><Trash2 /></button>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
      {connecting && <ConnectDialog provider={connecting} onClose={() => setConnecting(null)} onConnected={(id) => { bump(); setLinking(id) }} />}
      {linking && <LinkDialog cid={linking} accounts={(accounts.data?.items ?? []).filter((a) => a.country !== 'CA' && a.currency !== 'CAD')} onClose={() => setLinking(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function ConnectDialog({ provider, onClose, onConnected }) {
  const toast = useToast()
  const [token, setToken] = useState('')
  const [country, setCountry] = useState('DE')
  const [banks, setBanks] = useState(null)
  const [bank, setBank] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try {
      if (provider === 'gocardless') {
        const r = await api.post('/sync/gocardless/start', { institution_id: bank, redirect_url: `${location.origin}/sync` })
        sessionStorage.setItem('fv.gc.pending', r.connection_id)
        window.location.href = r.link
        return
      }
      const r = await api.post(`/sync/${provider}/connect`, { token })
      onConnected(r.connection_id); onClose()
    } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }
  const loadBanks = async () => { try { setBanks(await api.get(`/sync/gocardless/institutions${qs({ country })}`)) } catch (e) { toast(e.message, 'error') } }
  return (
    <Dialog title={t('Connect a bank')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className="btn primary" onClick={go} disabled={busy || (provider === 'gocardless' ? !bank : !token)}>{busy && <Loader2 className="spin" />}{t('Connect')}</button></>}>
      <div className="stack" style={{ gap: 14 }}>
        <p className="small muted"><ShieldCheck size={14} style={{ verticalAlign: -2 }} /> {t("Read-only access. The provider's credentials are stored encrypted on this server.")}</p>
        {provider === 'simplefin' && <Field label={t('SimpleFIN setup token')} hint={t('Create one at bridge.simplefin.org. A token can be claimed only once.')}><textarea className="input" value={token} onChange={(e) => setToken(e.target.value)} /></Field>}
        {provider === 'pluggy' && <Field label={t('Pluggy item ID')} hint={t('Connect your bank in MeuPluggy or the Pluggy dashboard, then paste the item ID.')}><input className="input" value={token} onChange={(e) => setToken(e.target.value)} /></Field>}
        {provider === 'gocardless' && (
          <>
            <div className="row" style={{ alignItems: 'end' }}>
              <Field label={t('Country')} className="grow"><select className="input" value={country} onChange={(e) => { setCountry(e.target.value); setBanks(null) }}>
                {['AT', 'BE', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GB', 'IE', 'IT', 'LT', 'LV', 'NL', 'NO', 'PL', 'PT', 'SE'].map((c) => <option key={c}>{c}</option>)}
              </select></Field>
              <button className="btn" onClick={loadBanks}>{t('Find banks')}</button>
            </div>
            {banks && <Field label={t('Bank')}><select className="input" value={bank} onChange={(e) => setBank(e.target.value)}><option value="">{t('Choose…')}</option>{banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>}
            <p className="small muted">{t("You'll be sent to your bank to approve access, then back here.")}</p>
          </>
        )}
      </div>
    </Dialog>
  )
}

function LinkDialog({ cid, accounts, onClose, onSaved }) {
  const toast = useToast()
  const remote = useData(() => api.get(`/sync/connections/${cid}/accounts`), [cid])
  const [choice, setChoice] = useState({})
  const link = async (ext) => {
    try {
      await api.post(`/sync/connections/${cid}/link`, { external_id: ext.id, account_id: choice[ext.id] ? Number(choice[ext.id]) : null })
      toast(t('Linked {name}', { name: ext.name })); onSaved(); remote.reload()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog wide title={t('Link provider accounts')} onClose={onClose} footer={<button className="btn primary" onClick={onClose}>{t('Done')}</button>}>
      {remote.error && <p className="error-text">{remote.error.message}</p>}
      {!remote.data ? <Loading rows={2} /> : remote.data.length === 0 ? <p className="muted">{t('The provider returned no accounts yet.')}</p> : (
        <div className="list card" style={{ boxShadow: 'none' }}>
          {remote.data.map((a) => (
            <div className="list-row" key={a.id}>
              <div className="grow"><div className="title">{a.name}</div><div className="meta">{a.currency}{a.domain ? ` · ${a.domain}` : ''}</div></div>
              {a.blocked ? (
                <span className="pill red" title={t('Canadian accounts are import only')}><Upload size={11} />{t('Canadian: import instead')}</span>
              ) : (
                <>
                  <select className="input sm" style={{ width: 200 }} value={choice[a.id] ?? ''} onChange={(e) => setChoice({ ...choice, [a.id]: e.target.value })}>
                    <option value="">{t('Create a new account')}</option>{accounts.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </select>
                  <button className="btn sm primary" onClick={() => link(a)}>{t('Link')}</button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </Dialog>
  )
}
