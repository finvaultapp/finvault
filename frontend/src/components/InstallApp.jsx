import { Download, Share } from 'lucide-react'
import { t } from '../i18n'
import { isIOS, isStandalone, promptInstall, useInstallPrompt } from '../lib/offline'

// Settings card: "Install app" where the browser offers it, Add to Home Screen steps on iPhone and iPad.
export default function InstallApp() {
  const prompt = useInstallPrompt()
  if (isStandalone()) return null
  const ios = isIOS()
  if (!prompt && !ios) return null
  return (
    <section className="card" id="install">
      <div className="card-head"><div>
        <h2>{t('Install app')}</h2>
        <div className="sub">{t('Put FinVault on your home screen. It opens in its own window and can show your last saved data when you are offline.')}</div>
      </div></div>
      <div className="card-body">
        {prompt ? (
          <button className="btn primary" onClick={promptInstall}><Download />{t('Install FinVault')}</button>
        ) : (
          <ol className="install-steps">
            <li>{t('Open this page in Safari.')}</li>
            <li><span>{t('Tap Share')}</span> <Share aria-hidden="true" /></li>
            <li>{t('Choose Add to Home Screen, then Add.')}</li>
          </ol>
        )}
        <p className="small muted install-note">{t('Saved data stays on this device until you sign out. On a shared phone, sign out when you are done.')}</p>
      </div>
    </section>
  )
}
