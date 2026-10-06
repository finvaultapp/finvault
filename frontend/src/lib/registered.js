// Registered accounts (TFSA, FHSA, RRSP): plan names and the movement type of each line.
// The codes come from the server (backend/app/importers/registered.py); labels translate at render time.
import { t } from '../i18n'

export const PLAN_KINDS = () => ({ tfsa: t('TFSA'), fhsa: t('FHSA'), rrsp: t('RRSP') })

export const PLAN_MOVES = () => ({
  contribution: t('Contribution'),
  withdrawal: t('Withdrawal'),
  transfer_in: t('Transfer in'),
  transfer_out: t('Transfer out'),
  rrsp_to_fhsa: t('RRSP to FHSA'),
  growth: t('Growth'),
  fee: t('Fee'),
  trade: t('Trade'),
  other: t('Other'),
})

// Same idea as suggest_kind on the server, for the account dialog while the member types a name.
const NOT_TRACKED = /\b(rrif|ferr|lif|frv|lira|cri|resp|reee|rdsp|reei)\b/
const WORDS = [
  ['fhsa', /\b(fhsa|celiapp|first home savings)\b/],
  ['tfsa', /\b(tfsa|celi|tax free savings)\b/],
  ['rrsp', /\b(rrsp|reer|rsp|registered retirement savings)\b/],
]

export function suggestKind(...texts) {
  const s = texts.join(' ').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ')
  if (NOT_TRACKED.test(s)) return null
  for (const [kind, re] of WORDS) if (re.test(s)) return kind
  return null
}
