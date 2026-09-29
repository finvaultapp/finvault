import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, MailCheck } from 'lucide-react'
import { api } from '../api'
import { t } from '../i18n'
import { Field } from '../components/ui'
import { AuthSolo } from './ResetPassword'

export default function ForgotPassword() {
  const [opts, setOpts] = useState(null)
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.get('/password-reset/options').then(setOpts).catch((e) => setError(e.message)) }, [])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try { await api.post('/password-reset/request', { email }); setSent(true) } catch (err) { setError(err.message) }
    setBusy(false)
  }

  const back = <p className="muted small" style={{ marginTop: 18 }}><Link to="/login">{t('Back to sign in')}</Link></p>

  if (sent) return (
    <AuthSolo>
      <h1>{t('Check your email')}</h1>
      <p className="muted reset-done"><MailCheck aria-hidden="true" />
        {t(opts.email_link_hours === 1 ? 'If {email} has an account here, a link to choose a new password is on its way. It works once, for 1 hour.'
          : 'If {email} has an account here, a link to choose a new password is on its way. It works once, for {hours} hours.', { email, hours: opts.email_link_hours })}</p>
      <p className="muted small">{t('Nothing after a few minutes? Check your spam folder, or ask your household admin for a reset link.')}</p>
      {back}
    </AuthSolo>
  )

  return (
    <AuthSolo>
      <h1>{t('Forgot your password?')}</h1>
      {!opts && !error && <p className="muted"><Loader2 size={16} className="spin" /></p>}
      {opts && !opts.local_auth && <p className="muted">{t('This server uses single sign-on only, so there is no FinVault password to reset.')}</p>}
      {opts?.local_auth && !opts.self_service && (
        <p className="muted">{t('This server can’t send reset emails. Ask your household admin: they can make you a one-time reset link from Admin, Members.')}</p>
      )}
      {opts?.self_service && (
        <>
          <p className="muted">{t('Enter the email you sign in with. We’ll send a link to choose a new password.')}</p>
          <form onSubmit={submit}>
            <Field label={t('Email')}><input className="input" type="email" required autoFocus autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            {error && <p className="error-text" role="alert">{error}</p>}
            <button className="btn primary" style={{ height: 40 }} disabled={busy}>{busy && <Loader2 size={16} className="spin" />}{t('Send reset link')}</button>
          </form>
        </>
      )}
      {!opts && error && <p className="error-text" role="alert">{error}</p>}
      {back}
    </AuthSolo>
  )
}
