// Opened from a one-time reset link: /reset-password#token=... (the token stays out of server logs).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Field } from '../components/ui'
import Logo from '../components/Logo'

const readToken = () => new URLSearchParams(window.location.hash.slice(1)).get('token') || ''

export function AuthSolo({ children }) {
  return (
    <div className="auth auth-solo">
      <div className="auth-panel">
        <div className="brand"><Logo />FinVault</div>
        {children}
      </div>
    </div>
  )
}

export default function ResetPassword() {
  const { user, setUser } = useApp()
  const [token] = useState(readToken)
  const [info, setInfo] = useState(null)
  const [linkError, setLinkError] = useState(token ? '' : t('This reset link is invalid, already used or expired. Ask for a new one.'))
  const [f, setF] = useState({ password: '', confirm: '', code: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    // Keep the token out of the address bar, history and screenshots once it has been read.
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname)
    if (!token) return
    api.post('/password-reset/check', { token }).then(setInfo).catch((e) => setLinkError(e.message))
  }, [token])

  const mismatch = f.confirm && f.password !== f.confirm
  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api.post('/password-reset/complete', { token, new_password: f.password, code: f.code })
      setDone(true)
      if (user && user.email === info.email) setUser(null) // this browser's session was signed out too
    } catch (err) {
      if (err.status === 400) setLinkError(err.message)
      else setError(err.message)
    }
    setBusy(false)
  }

  if (done) return (
    <AuthSolo>
      <h1>{t('Password changed')}</h1>
      <p className="muted reset-done"><CheckCircle2 aria-hidden="true" />{t('You were signed out everywhere. Sign in with your new password.')}</p>
      <Link className="btn primary auth-solo-btn" to={user && user.email !== info.email ? '/' : '/login'}>
        {user && user.email !== info.email ? t('Back to FinVault') : t('Sign in')}
      </Link>
    </AuthSolo>
  )

  if (linkError) return (
    <AuthSolo>
      <h1>{t('This link doesn’t work')}</h1>
      <p className="error-text" role="alert">{linkError}</p>
      <p className="muted small">{t('Ask your household admin for a new reset link, or use “Forgot password?” on the sign-in page if your server sends email.')}</p>
      <Link className="btn auth-solo-btn" to={user ? '/' : '/login'}>{user ? t('Back to FinVault') : t('Back to sign in')}</Link>
    </AuthSolo>
  )

  if (!info) return <AuthSolo><p className="muted" style={{ marginTop: 28 }}><Loader2 size={16} className="spin" /> {t('Checking the link…')}</p></AuthSolo>

  return (
    <AuthSolo>
      <h1>{t('Choose a new password')}</h1>
      <p className="muted">{t('For {email}. Once it’s changed, every device signed in to this account is signed out.', { email: info.email })}</p>
      <form onSubmit={submit}>
        <input type="email" hidden readOnly autoComplete="username" value={info.email} />
        <Field label={t('New password')} hint={t('At least 10 characters. A passphrase works well.')}>
          <input className="input" type="password" required autoFocus autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <Field label={t('New password again')} hint={mismatch ? t('The two passwords don’t match yet.') : null}>
          <input className="input" type="password" required autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} aria-invalid={mismatch || undefined} />
        </Field>
        {info.needs_2fa && (
          <Field label={t('Two-factor code')} hint={t('This account uses two-factor login. Enter the 6-digit code from your authenticator app, or one of your recovery codes. Lost both? Ask your admin to reset two-factor first.')}>
            <input className="input" required inputMode="text" autoComplete="one-time-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="123 456" />
          </Field>
        )}
        {error && <p className="error-text" role="alert">{error}</p>}
        <button className="btn primary" style={{ height: 40 }} disabled={busy || f.password.length < 10 || f.password !== f.confirm || (info.needs_2fa && !f.code.trim())}>
          {busy && <Loader2 size={16} className="spin" />}{t('Change password')}
        </button>
      </form>
    </AuthSolo>
  )
}
