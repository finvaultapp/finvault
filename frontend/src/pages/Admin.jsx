import { useState } from 'react'
import { AlertTriangle, Copy, KeyRound, Plus, ShieldOff, Trash2, UserPlus } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Confirm, Dialog, Field, Loading, PageHead, Switch, useData, useToast } from '../components/ui'
import { date } from '../lib/format'
import { t } from '../i18n'

export default function Admin() {
  const { user, refreshUser } = useApp()
  const toast = useToast()
  const users = useData(() => api.get('/admin/users'), [])
  const invites = useData(() => api.get('/admin/invites'), [])
  const settings = useData(() => api.get('/admin/settings'), [])
  const [confirm, setConfirm] = useState(null)
  const [creating, setCreating] = useState(false)
  const [ai, setAi] = useState(null)

  const patch = async (body) => {
    try { await api.patch('/admin/settings', body); settings.reload(); refreshUser(); toast(t('Settings saved')) } catch (e) { toast(e.message, 'error') }
  }
  const s = settings.data
  if (!s) return <Loading />
  const aiForm = ai ?? { ai_base_url: s.ai_base_url, ai_model: s.ai_model, ai_api_key: '', ai_max_transactions: s.ai_max_transactions }

  return (
    <>
      <PageHead title={t('Admin')} sub={t('Server-wide settings for everyone on this FinVault.')} />
      <div className="stack" style={{ maxWidth: 960 }}>
        <section className="card">
          <div className="card-head"><h2>{t('Members')}</h2><button className="btn sm" onClick={() => setCreating(true)}><UserPlus />{t('Add member')}</button></div>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>{t('Member')}</th><th className="hide-sm">{t('Joined')}</th><th className="hide-sm">{t('Data')}</th><th>{t('2FA')}</th><th>{t('Admin')}</th><th>{t('Active')}</th><th /></tr></thead>
            <tbody>{users.data?.map((u) => (
              <tr key={u.id}>
                <td><div className="strong">{u.name || u.email.split('@')[0]}{u.id === user.id && <span className="pill" style={{ marginLeft: 6 }}>{t('you')}</span>}</div><div className="small muted">{u.email}</div></td>
                <td className="hide-sm">{date(u.created_at)}</td>
                <td className="hide-sm small muted">{t(u.accounts === 1 ? '{n} account' : '{n} accounts', { n: u.accounts })} · {t(u.transactions === 1 ? '{n} transaction' : '{n} transactions', { n: u.transactions })}</td>
                <td>{u.totp_enabled ? <span className="pill green">{t('On')}</span> : <span className="pill">{t('Off')}</span>}</td>
                <td><Switch checked={u.is_admin} label={t('Admin')} onChange={async (v) => { try { await api.patch(`/admin/users/${u.id}`, { is_admin: v }); users.reload() } catch (e) { toast(e.message, 'error') } }} /></td>
                <td><Switch checked={u.is_active} label={t('Active')} onChange={async (v) => { try { await api.patch(`/admin/users/${u.id}`, { is_active: v }); users.reload() } catch (e) { toast(e.message, 'error') } }} /></td>
                <td><div className="row" style={{ gap: 0, justifyContent: 'flex-end' }}>
                  {u.totp_enabled && <button className="icon-btn" title={t('Reset two-factor')} aria-label={t('Reset two-factor')} onClick={() => setConfirm({ title: t('Reset two-factor for {email}?', { email: u.email }), body: t('Use this when a member lost their phone and recovery codes. They can sign in with just their password and set it up again.'), action: t('Reset'), onConfirm: async () => { await api.post(`/admin/users/${u.id}/reset-2fa`); users.reload() } })}><ShieldOff /></button>}
                  {u.id !== user.id && <button className="icon-btn" aria-label={t('Delete member')} onClick={() => setConfirm({ title: t('Delete {email}?', { email: u.email }), body: t('This permanently deletes their {accounts} accounts and {transactions} transactions.', { accounts: u.accounts, transactions: u.transactions }), onConfirm: async () => { await api.del(`/admin/users/${u.id}`); users.reload() } })}><Trash2 /></button>}
                </div></td>
              </tr>
            ))}</tbody>
          </table></div>
        </section>

        <section className="card">
          <div className="card-head"><div><h2>{t('Registration')}</h2><div className="sub">{t('Who can create an account on this server.')}</div></div></div>
          <div className="card-body stack" style={{ gap: 16 }}>
            <div className="segmented" style={{ width: 'fit-content' }}>
              {[['open', 'Anyone who can reach it'], ['invite', 'Invite code only'], ['closed', 'Closed']].map(([k, l]) => (
                <button key={k} className={s.registration_mode === k ? 'on' : ''} onClick={() => patch({ registration_mode: k })}>{t(l)}</button>
              ))}
            </div>
            {s.registration_mode === 'open' && <div className="banner warn"><AlertTriangle /><div className="banner-body">{t('Anyone who can open this address can sign up. Only use this on a private home network.')}</div></div>}
            {s.registration_mode === 'invite' && (
              <>
                <div className="row"><button className="btn sm" onClick={async () => { const r = await api.post('/admin/invites', { days: 7 }); navigator.clipboard?.writeText(r.code); invites.reload(); toast(t('Invite code created and copied')) }}><Plus />{t('New invite code')}</button><span className="small muted">{t('Codes work once and expire after 7 days.')}</span></div>
                {invites.data?.filter((i) => !i.used).length > 0 && (
                  <div className="list card" style={{ boxShadow: 'none' }}>
                    {invites.data.filter((i) => !i.used).map((i) => (
                      <div className="list-row" key={i.id} style={{ padding: '9px 14px' }}>
                        <KeyRound size={16} className="muted" />
                        <code className="grow" style={{ userSelect: 'all' }}>{i.code}</code>
                        <span className="small muted">{t('expires {date}', { date: date(i.expires_at) })}</span>
                        <button className="icon-btn" aria-label={t('Copy')} onClick={() => navigator.clipboard?.writeText(i.code)}><Copy /></button>
                        <button className="icon-btn" aria-label={t('Revoke')} onClick={async () => { await api.del(`/admin/invites/${i.id}`); invites.reload() }}><Trash2 /></button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head"><div><h2>{t('Optional features')}</h2><div className="sub">{t('All off by default. Each one is a choice to send something outside this server.')}</div></div></div>
          <div className="list">
            <Toggle checked={s.bank_sync_enabled} onChange={(v) => patch({ bank_sync_enabled: v })} title={t('Bank sync')}
              desc={t("Lets members connect non-Canadian banks through GoCardless (EU), Pluggy (Brazil) or SimpleFIN (US) when credentials are set in the server's .env. Canadian accounts are never synced.")} />
            {s.bank_sync_enabled && <Toggle checked={s.simplefin_enabled} onChange={(v) => patch({ simplefin_enabled: v })} title={t('Allow SimpleFIN')} desc={t('Members bring their own SimpleFIN setup token.')} />}
            <Toggle checked={s.folder_import_enabled} onChange={(v) => patch({ folder_import_enabled: v })} title={t('Watched import folder')}
              desc={t('Members can pick accounts whose bank exports are imported from a folder on this server (mount your NAS share at /inbox).')} />
            <Toggle checked={s.ocr_enabled} onChange={(v) => patch({ ocr_enabled: v })} title={t('Read text from receipts')}
              desc={t('Runs Tesseract OCR on this server for uploaded receipt photos, so receipt text is searchable. Nothing leaves the server.')} />
            <Toggle checked={s.fx_fetch_enabled} onChange={(v) => patch({ fx_fetch_enabled: v })} title={t('Fetch exchange rates')} desc={t('Adds a button to download ECB reference rates. Only currency codes are sent.')} />
            <Toggle checked={s.ai_enabled} onChange={(v) => patch({ ai_enabled: v })} title={t('Household AI model')} desc={t('Members who opt in can ask questions about their own data. Point it at a model you host, like Ollama.')} />
            <Toggle checked={s.ai_allow_personal_keys} onChange={(v) => patch({ ai_allow_personal_keys: v })} title={t('Let members connect their own ChatGPT (OpenAI) account')}
              desc={t('Each member can add their own OpenAI API key, billed to them. Their questions, with a summary of their data, go to OpenAI.')} />
          </div>
          {s.ai_enabled && (
            <div className="card-body" style={{ borderTop: '1px solid var(--border)' }}>
              {!s.ai_endpoint_is_local && <div className="banner warn" style={{ marginBottom: 14 }}><AlertTriangle /><div className="banner-body">{t("This endpoint isn't on a local network. Members' financial data will be sent to it when they chat.")}</div></div>}
              <div className="form-grid">
                <Field label={t('Model endpoint (OpenAI-compatible)')} hint="Ollama: http://ollama:11434/v1"><input className="input" value={aiForm.ai_base_url} onChange={(e) => setAi({ ...aiForm, ai_base_url: e.target.value })} /></Field>
                <Field label={t('Model')}><input className="input" value={aiForm.ai_model} onChange={(e) => setAi({ ...aiForm, ai_model: e.target.value })} /></Field>
                <Field label={t('API key')} hint={s.ai_api_key_set ? t('A key is saved. Leave empty to keep it.') : t('Not needed for Ollama.')}><input className="input" type="password" value={aiForm.ai_api_key} onChange={(e) => setAi({ ...aiForm, ai_api_key: e.target.value })} /></Field>
                <Field label={t('Recent transactions shared per question')}><input className="input" type="number" min="0" max="5000" value={aiForm.ai_max_transactions} onChange={(e) => setAi({ ...aiForm, ai_max_transactions: Number(e.target.value) })} /></Field>
              </div>
              <button className="btn primary" style={{ marginTop: 14 }} onClick={() => { const b = { ...aiForm }; if (!b.ai_api_key) delete b.ai_api_key; patch(b); setAi(null) }}>{t('Save AI settings')}</button>
            </div>
          )}
        </section>
      </div>
      {creating && <CreateUser onClose={() => setCreating(false)} onSaved={users.reload} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function Toggle({ checked, onChange, title, desc }) {
  return (
    <div className="list-row">
      <div className="grow"><div className="strong">{title}</div><div className="small muted">{desc}</div></div>
      <Switch checked={checked} onChange={onChange} label={title} />
    </div>
  )
}

function CreateUser({ onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ email: '', name: '', password: '', is_admin: false })
  const save = async () => { try { await api.post('/admin/users', f); onSaved(); onClose(); toast(t('Member added')) } catch (e) { toast(e.message, 'error') } }
  return (
    <Dialog title={t('Add a household member')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!f.email || f.password.length < 10}>{t('Add member')}</button></>}>
      <div className="form-grid">
        <Field label={t('Name')}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Email')}><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label={t('Temporary password')} hint={t('At least 10 characters. Ask them to change it in Settings.')} className="full"><input className="input" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <label className="check full"><input type="checkbox" checked={f.is_admin} onChange={(e) => setF({ ...f, is_admin: e.target.checked })} /><span>{t('Make admin')}<small>{t("Admins manage members and server settings. They can't see other members' data.")}</small></span></label>
      </div>
    </Dialog>
  )
}
