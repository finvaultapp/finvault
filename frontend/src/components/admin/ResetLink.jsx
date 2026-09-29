// Admin, Members: make a one-time password reset link for a member. The admin never sees or picks the password.
import { useState } from 'react'
import { Copy, KeyRound, Loader2 } from 'lucide-react'
import { api } from '../../api'
import { t } from '../../i18n'
import { Dialog, useToast } from '../ui'
import { currentLocale } from '../../lib/format'

const dateTime = (iso) => new Date(iso).toLocaleString(currentLocale(), { dateStyle: 'medium', timeStyle: 'short' })

export default function ResetLinkButton({ member }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="icon-btn" title={t('Reset password')} aria-label={t('Reset password')} onClick={() => setOpen(true)}><KeyRound /></button>
      {open && <ResetLinkDialog member={member} onClose={() => setOpen(false)} />}
    </>
  )
}

function ResetLinkDialog({ member, onClose }) {
  const toast = useToast()
  const [link, setLink] = useState(null)
  const [busy, setBusy] = useState(false)
  const make = async () => {
    setBusy(true)
    try { setLink(await api.post(`/admin/users/${member.id}/password-reset`)) } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }
  const url = link ? (link.url ?? `${window.location.origin}${link.path}`) : ''
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast(t('Reset link copied')) } catch { toast(t('Couldn’t copy. Select the link and copy it yourself.'), 'error') }
  }
  const who = member.name || member.email
  return (
    <Dialog title={t('Reset password for {email}', { email: member.email })} onClose={onClose} footer={link
      ? <><button className="btn" onClick={copy}><Copy />{t('Copy link')}</button><button className="btn primary" onClick={onClose}>{t('Done')}</button></>
      : <><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={make} disabled={busy}>{busy && <Loader2 className="spin" />}{t('Make reset link')}</button></>}>
      {!link ? (
        <div className="stack" style={{ gap: 12 }}>
          <p className="muted">{t('FinVault makes a one-time link where {name} chooses a new password. You never see or pick it. The link works for 24 hours, and making a new one cancels the old one.', { name: who })}</p>
          <p className="muted">{t('Their current password keeps working until they use the link. Using it signs them out on every device.')}</p>
          {member.totp_enabled && <div className="banner info"><KeyRound /><div className="banner-body">{t('They have two-factor login on, so the reset page also asks for their authenticator or recovery code. If they lost those too, reset two-factor as well.')}</div></div>}
        </div>
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          <p className="muted">{t('Give this link to {name} in person or in a message only they can read. Anyone with it can set the password.', { name: who })}</p>
          <input className="input reset-link-url" readOnly value={url} aria-label={t('Reset link')} onFocus={(e) => e.target.select()} />
          <p className="small muted">{t('Works once, until {when}.', { when: dateTime(link.expires_at) })}{!link.url && ` ${t('Built from the address you opened FinVault at. Set PUBLIC_URL on the server if members use a different one.')}`}</p>
        </div>
      )}
    </Dialog>
  )
}
