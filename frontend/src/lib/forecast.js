// Plain-language low-balance warnings, shared by the Forecast page and the dashboard banner.
import { t } from '../i18n'
import { date, money } from './format'

export function warningSentence(w) {
  const vars = { account: w.account_name, date: date(w.date, { month: 'short', day: 'numeric' }), amount: money(w.balance, w.currency),
    cushion: money(w.cushion, w.currency), bill: w.bill?.name ?? '', due: w.bill ? date(w.bill.date, { month: 'short', day: 'numeric' }) : '' }
  if (w.code === 'already_below') {
    return w.cushion > 0 ? t('{account} is already below your {cushion} cushion.', vars) : t('{account} is already below $0.', vars)
  }
  if (w.bill && w.bill.date === w.date) {
    return w.cushion > 0
      ? t('{account} could drop to {amount} on {date} when {bill} comes out, below your {cushion} cushion.', vars)
      : t('{account} could drop to {amount} on {date} when {bill} comes out.', vars)
  }
  if (w.bill) {
    return w.cushion > 0
      ? t('{account} could be down to {amount} by {date}, below your {cushion} cushion, before {bill} on {due}.', vars)
      : t('{account} could be down to {amount} by {date}, before {bill} on {due}.', vars)
  }
  return w.cushion > 0
    ? t('{account} could be down to {amount} by {date}, below your {cushion} cushion.', vars)
    : t('{account} could be down to {amount} by {date}.', vars)
}
