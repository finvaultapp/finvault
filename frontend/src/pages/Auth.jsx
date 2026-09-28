import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FileDown, HardDrive, KeyRound, Loader2, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { useI18n } from '../i18n'
import { t } from '../i18n'
import { Field } from '../components/ui'
import Logo from '../components/Logo'
import { CURRENCIES } from '../lib/format'

export default function Auth({ mode }) {
  const { status, setUser, refreshUser } = useApp()
  const { locale } = useI18n()
  const navigate = useNavigate()
  const setup = status?.needs_setup
  const registering = mode === 'register' || setup
  const [form, setForm] = useState({ email: '', password: '', name: '', invite_code: new URLSearchParams(location.search).get('invite') ?? '', base_currency: 'CAD' })
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (challenge) {
        const r = await api.post('/auth/login/2fa', { challenge, code })
        setUser(r.user)
      } else if (registering) {
        setUser(await api.post('/auth/register', { ...form, locale }))
        await refreshUser()
      } else {
        const r = await api.post('/auth/login', { email: form.email, password: form.password })
        if (r.requires_2fa) { setChallenge(r.challenge); setBusy(false); return }
        setUser(r.user)
      }
      navigate('/')
    } catch (err) {
      setError(err.message)
      if (challenge && err.status === 401 && /expired/i.test(err.detail ?? err.message)) setChallenge(null)
    }
    setBusy(false)
  }

  const regMode = status?.registration_mode
  return (
    <div className="auth">
      <div className="auth-panel">
        <div className="brand"><Logo />FinVault</div>
        <h1>{challenge ? t('Two-factor check') : setup ? t('Set up your FinVault') : registering ? t('Create your account') : t('Sign in')}</h1>
        <p className="muted">
          {challenge ? t('Enter the 6-digit code from your authenticator app, or one of your recovery codes.')
            : setup ? t('This first account becomes the admin for your household server.')
            : registering ? (regMode === 'invite' ? t('Ask your household admin for an invite code.') : t('Your data stays on this server.'))
            : t('Welcome back. Your data stays on this server.')}
        </p>
        <form onSubmit={submit}>
          {challenge ? (
            <Field label={t('Authentication code')}>
              <input className="input" inputMode="numeric" autoComplete="one-time-code" autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="123 456" />
            </Field>
          ) : (
            <>
              {registering && <Field label={t('Your name')}><input className="input" value={form.name} onChange={set('name')} autoComplete="name" /></Field>}
              <Field label={t('Email')}><input className="input" type="email" required value={form.email} onChange={set('email')} autoComplete="email" autoFocus /></Field>
              <Field label={t('Password')} hint={registering ? t('At least 10 characters. A passphrase works well.') : null}>
                <input className="input" type="password" required value={form.password} onChange={set('password')} autoComplete={registering ? 'new-password' : 'current-password'} />
              </Field>
              {registering && !setup && regMode === 'invite' && (
                <Field label={t('Invite code')}><input className="input" required value={form.invite_code} onChange={set('invite_code')} /></Field>
              )}
              {registering && (
                <Field label={t('Main currency')} hint={t('Reports and net worth are shown in this currency.')}>
                  <select className="input" value={form.base_currency} onChange={set('base_currency')}>
                    {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Field>
              )}
            </>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
          <button className="btn primary" disabled={busy} style={{ height: 40 }}>
            {busy && <Loader2 size={16} className="spin" />}
            {challenge ? t('Verify') : registering ? t('Create account') : t('Sign in')}
          </button>
        </form>
        {!setup && !challenge && (
          <p className="muted small" style={{ marginTop: 18 }}>
            {registering ? <>{t('Already have an account?')} <Link to="/login">{t('Sign in')}</Link></>
              : regMode !== 'closed' ? <>{t('New to this household?')} <Link to="/register">{t('Create an account')}</Link></> : t('Accounts on this server are created by the admin.')}
          </p>
        )}
      </div>
      <aside className="auth-aside">
        <h2>{t('Every statement, sorted. On your own hardware.')}</h2>
        <div className="mini-wall" aria-hidden="true">
          {[['Groceries', '#C8792F', '72%'], ['Rent', '#8A5A44', '100%'], ['Dining', '#C44536', '38%'], ['Fuel', '#3F7580', '55%'],
            ['Phone', '#5A7AA6', '90%'], ['Kids', '#B08A3F', '24%'], ['Travel', '#3F8FA8', '12%'], ['Gifts', '#9A8A5A', '46%']].map(([n, c, h]) => (
            <span key={n} style={{ '--c': c, '--h': h }}><b>{t(n)}</b></span>
          ))}
        </div>
        <ul>
          <li><HardDrive /><div><strong>{t('Stays on this server')}</strong><br /><span>{t('Accounts, transactions and reports live in your own database.')}</span></div></li>
          <li><FileDown /><div><strong>{t('No bank passwords, ever')}</strong><br /><span>{t('Import the QFX, OFX or CSV file your bank already gives you. Canadian accounts never connect directly.')}</span></div></li>
          <li><ShieldCheck /><div><strong>{t('Separate logins')}</strong><br /><span>{t('Each member has their own data, with optional two-factor sign-in.')}</span></div></li>
          <li><KeyRound /><div><strong>{t('Extras stay off')}</strong><br /><span>{t('Bank sync and AI chat are off until an admin turns them on.')}</span></div></li>
        </ul>
      </aside>
    </div>
  )
}
