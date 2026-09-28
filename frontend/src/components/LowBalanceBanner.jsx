// Dashboard banner: shown only when the cash-flow forecast sees a chequing account dipping too low.
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { warningSentence } from '../lib/forecast'
import { useData } from './ui'

export default function LowBalanceBanner() {
  const { version } = useApp()
  const { data } = useData(() => api.get('/forecast/warnings').catch(() => null), [version])
  const warnings = data?.warnings ?? []
  if (!warnings.length) return null
  const first = warnings[0]
  return (
    <div className="banner warn low-balance" role="alert">
      <AlertTriangle />
      <div className="banner-body">
        <strong>{t('Low balance ahead.')}</strong> {warningSentence(first)}
        {warnings.length > 1 && <> {t(warnings.length === 2 ? 'One more account too.' : '{n} more accounts too.', { n: warnings.length - 1 })}</>}{' '}
        <Link to="/forecast">{t('See the forecast')}</Link> <span className="muted small">({t('an estimate')})</span>
      </div>
    </div>
  )
}
