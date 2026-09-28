import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Copy, Download, Eye, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Dialog, Field, Loading, PageHead, Switch, useData, useToast } from '../components/ui'
import { CURRENCIES, date, todayISO } from '../lib/format'
import { LANGUAGES, t, useI18n } from '../i18n'
import InstallApp from '../components/InstallApp'

export default function Settings() {
  const { hash } = useLocation()
  useEffect(() => { if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }) }, [hash])
  return (
    <>
      <PageHead title={t('Settings')} />
      <div className="stack" style={{ maxWidth: 860 }}>
        <Profile />
        <Currency />
        <Security />
        <AiOptIn />
        <InstallApp />
      </div>
    </>
  )
}

function Section({ id, title, sub, children }) {
  return (
    <section className="card" id={id} style={{ scrollMarginTop: 20 }}>
      <div className="card-head"><div><h2>{title}</h2>{sub && <div className="sub">{sub}</div>}</div></div>
      <div className="card-body">{children}</div>
    </section>
  )
}

function Profile() {
  const { user, setUser, bump } = useApp()
  const toast = useToast()
  const [name, setName] = useState(user.name)
  const [base, setBase] = useState(user.base_currency)
  const { locale, setLocale } = useI18n()
  const save = async () => { setUser(await api.patch('/auth/me', { name, base_currency: base })); bump(); toast(t('Profile saved')) }
  const changeLanguage = async (next) => { setLocale(next); setUser(await api.patch('/auth/me', { locale: next })); bump() }
  return (
    <Section title={t('Profile')}>
      <div className="form-grid">
        <Field label={t('Name')}><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label={t('Email')}><input className="input" value={user.email} disabled /></Field>
        <Field label={t('Main currency')} hint={t('Totals, budgets and reports are converted into this currency.')}>
          <select className="input" value={base} onChange={(e) => setBase(e.target.value)}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select>
        </Field>
        <Field label={t('Language')} hint={t('Changes the whole app, including dates and money (1 234,56 $ in French).')}>
          <select className="input" value={locale} onChange={(e) => changeLanguage(e.target.value)}>
            {Object.entries(LANGUAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
      </div>
      <button className="btn primary" style={{ marginTop: 16 }} onClick={save}>{t('Save profile')}</button>
    </Section>
  )
}

function Currency() {
  const { user, bump } = useApp()
  const toast = useToast()
  const status = useData(() => api.get('/currency/status'), [user.base_currency])
  const rates = useData(() => api.get('/currency/rates'), [])
  const [f, setF] = useState({ base: '', quote: user.base_currency, rate: '', date: todayISO() })
  const add = async (base = f.base) => {
    try {
      await api.post('/currency/rates', { ...f, base, rate: Number(f.rate) })
      toast(t('Rate saved')); setF({ ...f, base: '', rate: '' }); status.reload(); rates.reload(); bump()
    } catch (e) { toast(e.message, 'error') }
  }
  const fetchRates = async () => {
    try { const r = await api.post('/currency/rates/fetch'); toast(t(r.updated === 1 ? 'Updated {n} rate' : 'Updated {n} rates', { n: r.updated })); status.reload(); rates.reload(); bump() } catch (e) { toast(e.message, 'error') }
  }
  const s = status.data
  return (
    <Section id="currency" title={t('Exchange rates')} sub={t('Used to convert other currencies into {currency}. Rates are shared by everyone on this server.', { currency: user.base_currency })}>
      {!s ? <Loading rows={2} /> : (
        <div className="stack" style={{ gap: 16 }}>
          {s.missing.length > 0 ? (
            <div className="banner warn"><AlertTriangle /><div className="banner-body"><strong>{t('Missing rates:')}</strong> {t('{pairs}. Amounts in {currencies} are left out of your totals until you add a rate.', { pairs: s.missing.map((c) => `${c} → ${s.base_currency}`).join(', '), currencies: s.missing.join(', ') })}</div></div>
          ) : s.pairs.length > 0 ? (
            <div className="banner info"><CheckCircle2 /><div className="banner-body">{t('Every currency you use can be converted to {currency}.', { currency: s.base_currency })}</div></div>
          ) : <p className="muted">{t('All your accounts are in {currency}; no rates needed.', { currency: s.base_currency })}</p>}
          {s.pairs.length > 0 && (
            <div className="row wrap" style={{ gap: 8 }}>
              {s.pairs.map((p) => <span key={p.currency} className={`pill ${p.rate ? '' : 'amber'}`}>1 {p.currency} = {p.rate ? `${p.rate.toFixed(4)} ${s.base_currency}` : t('no rate')}</span>)}
            </div>
          )}
          <div className="form-grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr)) auto', alignItems: 'end' }}>
            <Field label={t('1 unit of')}><select className="input" value={f.base} onChange={(e) => setF({ ...f, base: e.target.value })}>
              <option value="">{t('Currency…')}</option>{CURRENCIES.filter((c) => c !== f.quote).map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label={t('equals')}><input className="input" type="number" step="0.0001" min="0" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} placeholder="1.3650" /></Field>
            <Field label={t('in currency')}><select className="input" value={f.quote} onChange={(e) => setF({ ...f, quote: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label={t('From date')}><input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
            <button className="btn primary" onClick={() => add()} disabled={!f.base || !f.rate}>{t('Add rate')}</button>
          </div>
          {s.fetch_enabled && <div><button className="btn" onClick={fetchRates}><RefreshCw />{t("Fetch today's ECB rates")}</button> <span className="small muted">{t('Sends only currency codes to the rate service.')}</span></div>}
          {rates.data?.length > 0 && (
            <div className="table-wrap card" style={{ boxShadow: 'none', maxHeight: 260, overflowY: 'auto' }}>
              <table className="table"><thead><tr><th>{t('Pair')}</th><th>{t('Rate')}</th><th>{t('Starting')}</th><th>{t('Source')}</th><th /></tr></thead>
                <tbody>{rates.data.map((r) => (
                  <tr key={r.id}><td>{r.base} → {r.quote}</td><td className="num">{r.rate}</td><td>{date(r.date)}</td><td className="muted">{r.source === 'ecb' ? t('ECB') : t('Manual')}</td>
                    <td><button className="icon-btn" aria-label={t('Delete rate')} onClick={async () => { await api.del(`/currency/rates/${r.id}`); rates.reload(); status.reload(); bump() }}><Trash2 /></button></td></tr>
                ))}</tbody></table>
            </div>
          )}
          <p className="small muted">{t("For each date FinVault uses the latest rate on or before it (or the oldest one you've entered). Inverse and one-step cross rates are worked out automatically.")}</p>
        </div>
      )}
    </Section>
  )
}

function Security() {
  const { user, setUser } = useApp()
  const toast = useToast()
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [setup, setSetup] = useState(null)
  const [disabling, setDisabling] = useState(false)
  const changePw = async () => {
    try { await api.post('/auth/password', pw); setPw({ current_password: '', new_password: '' }); toast(t('Password changed. Other devices were signed out.')) } catch (e) { toast(e.message, 'error') }
  }
  const logoutAll = async () => { await api.post('/auth/logout-all'); setUser(null) }
  return (
    <Section id="security" title={t('Sign-in and security')}>
      <div className="stack" style={{ gap: 22 }}>
        <div className="row wrap" style={{ gap: 16 }}>
          <ShieldCheck className="row-icon" aria-hidden="true" />
          <div className="grow">
            <div className="strong">{user.totp_enabled ? t('Two-factor login is on') : t('Two-factor login is off')}</div>
            <div className="small muted">{t('Ask for a code from an authenticator app (Aegis, 2FAS, 1Password, Google Authenticator) at sign-in.')}</div>
          </div>
          {user.totp_enabled ? <button className="btn danger" onClick={() => setDisabling(true)}>{t('Turn off')}</button>
            : <button className="btn primary" onClick={async () => setSetup(await api.post('/auth/2fa/setup'))}>{t('Turn on')}</button>}
        </div>
        <div className="divider" style={{ margin: 0 }} />
        <div>
          <div className="strong" style={{ marginBottom: 10 }}>{t('Change password')}</div>
          <div className="form-grid">
            <Field label={t('Current password')}><input className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label={t('New password')} hint={t('At least 10 characters.')}><input className="input" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn" onClick={changePw} disabled={!pw.current_password || pw.new_password.length < 10}>{t('Change password')}</button>
            <span className="spacer" />
            <button className="btn ghost" onClick={logoutAll}>{t('Sign out on all devices')}</button>
          </div>
        </div>
      </div>
      {setup && <TotpSetup setup={setup} onClose={() => setSetup(null)} onDone={(u) => setUser({ ...user, totp_enabled: true })} />}
      {disabling && <TotpDisable onClose={() => setDisabling(false)} onDone={() => setUser({ ...user, totp_enabled: false })} />}
    </Section>
  )
}

function TotpSetup({ setup, onClose, onDone }) {
  const toast = useToast()
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState(null)
  const enable = async () => {
    try { const r = await api.post('/auth/2fa/enable', { code }); setCodes(r.recovery_codes); onDone() } catch (e) { toast(e.message, 'error') }
  }
  const download = () => {
    const blob = new Blob([`${t('FinVault recovery codes')}\n${t('Each code works once.')}\n\n${codes.join('\n')}\n`], { type: 'text/plain' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'finvault-recovery-codes.txt'; a.click()
  }
  if (codes) return (
    <Dialog title={t('Save your recovery codes')} onClose={onClose} footer={<><button className="btn" onClick={download}><Download />{t('Download')}</button><button className="btn primary" onClick={onClose}>{t("I've saved them")}</button></>}>
      <p className="muted" style={{ marginBottom: 14 }}>{t("If you lose your phone, each of these codes lets you sign in once. They won't be shown again.")}</p>
      <div className="codes">{codes.map((c) => <span key={c}>{c}</span>)}</div>
    </Dialog>
  )
  return (
    <Dialog title={t('Turn on two-factor login')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={enable} disabled={code.length < 6}>{t('Verify and turn on')}</button></>}>
      <div className="stack" style={{ gap: 14 }}>
        <p className="muted">{t('1. Scan this QR code with your authenticator app.')}</p>
        <div className="qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
        <p className="small muted">{t("Can't scan? Enter this key:")} <code style={{ userSelect: 'all' }}>{setup.secret}</code>{' '}
          <button className="link-btn" onClick={() => navigator.clipboard?.writeText(setup.secret)}><Copy size={13} />{t('Copy')}</button></p>
        <Field label={t('2. Enter the 6-digit code it shows')}><input className="input" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} /></Field>
      </div>
    </Dialog>
  )
}

function TotpDisable({ onClose, onDone }) {
  const toast = useToast()
  const [f, setF] = useState({ password: '', code: '' })
  const go = async () => { try { await api.post('/auth/2fa/disable', f); onDone(); onClose(); toast(t('Two-factor login turned off')) } catch (e) { toast(e.message, 'error') } }
  return (
    <Dialog title={t('Turn off two-factor login')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn danger" onClick={go}>{t('Turn off')}</button></>}>
      <div className="form-grid">
        <Field label={t('Password')}><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <Field label={t('Current code')}><input className="input" inputMode="numeric" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>
      </div>
    </Dialog>
  )
}

function AiOptIn() {
  const { user, setUser, refreshUser, bump } = useApp()
  const toast = useToast()
  const [tick, setTick] = useState(0)
  const status = useData(() => api.get('/ai/status'), [user.ai_opt_in, tick])
  const [key, setKey] = useState('')
  const [models, setModels] = useState(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const s = status.data
  if (!s?.available) return null

  const reload = () => { setTick((n) => n + 1); refreshUser(); bump() }
  const toggle = async (v) => { setUser(await api.patch('/auth/me', { ai_opt_in: v })); reload() }
  const choose = async (provider) => {
    try { await api.put('/ai/personal', { provider }); reload() } catch (e) { toast(e.message, 'error') }
  }
  const connect = async () => {
    setBusy(true)
    try {
      await api.put('/ai/personal', { provider: 'openai', api_key: key })
      setKey('')
      setModels((await api.get('/ai/personal/models')).models)
      toast(t('OpenAI account connected'))
      reload()
    } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }
  const loadModels = async () => { try { setModels((await api.get('/ai/personal/models')).models) } catch (e) { toast(e.message, 'error') } }
  const loadPreview = async () => { try { setPreview(await api.get('/ai/context-preview')) } catch (e) { toast(e.message, 'error') } }
  const pickModel = async (model) => { await api.put('/ai/personal', { provider: 'openai', model }); reload() }
  const disconnect = async () => { await api.del('/ai/personal'); setModels(null); toast(t('OpenAI key removed')); reload() }

  const usingOpenAI = s.provider === 'openai'
  return (
    <Section id="ai" title={t('AI assistant')} sub={t('Ask questions about your own money. Off until you choose to turn it on, and only you see your chats.')}>
      <div className="stack" style={{ gap: 18 }}>
        <div className="ai-choice" role="radiogroup" aria-label={t('Which AI to use')}>
          {s.server_enabled && (
            <button role="radio" aria-checked={!usingOpenAI} className={!usingOpenAI ? 'on' : ''} onClick={() => choose('server')}>
              <span className="strong">{t('Household model')}</span>
              <span className="small muted">{s.endpoint_is_local && !usingOpenAI ? t('{model} on your server. Data stays on your network.', { model: s.server_model }) : t('{model} on your server.', { model: s.server_model })}</span>
            </button>
          )}
          {s.personal_allowed && (
            <button role="radio" aria-checked={usingOpenAI} className={usingOpenAI ? 'on' : ''} onClick={() => choose('openai')}>
              <span className="strong">{t('My ChatGPT (OpenAI) account')}</span>
              <span className="small muted">{t('Uses your own OpenAI API key. Answers are billed to your OpenAI account.')}</span>
            </button>
          )}
        </div>

        {usingOpenAI && (
          <div className="card" style={{ boxShadow: 'none' }}>
            <div className="card-body stack" style={{ gap: 14 }}>
              {!s.personal.key_set ? (
                <>
                  <p className="small muted">
                    {t("A ChatGPT Plus or Pro subscription can't be used by other apps. Create an API key instead at")}{' '}
                    <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer noopener">platform.openai.com/api-keys</a>{' '}
                    {t('(you may need to add a small amount of credit), then paste it here. FinVault checks it with OpenAI and stores it encrypted on this server.')}
                  </p>
                  <div className="row wrap" style={{ alignItems: 'flex-end' }}>
                    <Field label={t('OpenAI API key')} className="grow"><input className="input" type="password" autoComplete="off" placeholder="sk-..." value={key} onChange={(e) => setKey(e.target.value)} /></Field>
                    <button className="btn primary" onClick={connect} disabled={busy || key.trim().length < 20}>{busy ? t('Checking…') : t('Connect')}</button>
                  </div>
                </>
              ) : (
                <>
                  <div className="row wrap">
                    <span className="pill green">{t('Connected')}</span>
                    <span className="small muted">{t('Your key is saved encrypted. It is never shown again.')}</span>
                    <span className="spacer" />
                    <button className="btn sm danger" onClick={disconnect}>{t('Remove key')}</button>
                  </div>
                  <div className="row wrap" style={{ alignItems: 'flex-end' }}>
                    <Field label={t('Model')} className="grow" hint={t('The list comes from your OpenAI account, so it only shows models your key can use.')}>
                      {models ? (
                        <select className="input" value={s.personal.model ?? ''} onChange={(e) => pickModel(e.target.value)}>
                          {!models.includes(s.personal.model) && s.personal.model && <option value={s.personal.model}>{s.personal.model}</option>}
                          {models.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                      ) : <input className="input" value={s.personal.model ?? ''} readOnly />}
                    </Field>
                    {!models && <button className="btn" onClick={loadModels}>{t('Change model')}</button>}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        <div className="row" style={{ gap: 14 }}>
          <Switch checked={user.ai_opt_in} onChange={toggle} label={t('Allow AI chat')} />
          <div className="grow">
            <div className="strong">{t('Let the AI read my finance data when I ask it something')}</div>
            <div className="small muted">
              {usingOpenAI
                ? t('Each question sends a summary of your accounts, budgets and recent transactions to OpenAI. Nothing is sent until you ask.')
                : s.endpoint_is_local ? t('The model runs on your own network.') : t('Heads up: the model endpoint is not on your local network, so your data is sent to it.')}
            </div>
          </div>
        </div>
        <div>
          <button className="btn" onClick={loadPreview}><Eye />{t('Preview data shared with AI')}</button>
        </div>
        {s.ready && <p className="small">{t('Ready. Open')} <Link to="/chat">{t('Ask AI')}</Link> {t('from the sidebar.')}</p>}
      </div>
      {preview && <AiPreview preview={preview} onClose={() => setPreview(null)} />}
    </Section>
  )
}

function AiPreview({ preview, onClose }) {
  return (
    <Dialog title={t('Data shared with AI')} onClose={onClose} footer={<button className="btn primary" onClick={onClose}>{t('Done')}</button>}>
      <div className="stack" style={{ gap: 12 }}>
        <p className="small muted">
          {preview.model
            ? t('{provider} receives this summary with each question. Recent transactions included: {n}.', { provider: preview.provider, n: preview.max_transactions })
            : t('No AI model is selected yet, but this is the summary FinVault will prepare once AI is set up.')}
        </p>
        <pre className="json-preview">{JSON.stringify(preview.data, null, 2)}</pre>
      </div>
    </Dialog>
  )
}
