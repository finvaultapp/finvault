import { useEffect, useState } from 'react'
import { api } from '../api'
import { Dialog, Field, useToast } from './ui'
import { CategorySelect } from './TxDialog'
import { money, date } from '../lib/format'
import { t } from '../i18n'

// Suggest a readable pattern from a raw bank description: "LOBLAWS #1234 TORONTO" -> "loblaws".
function suggestPattern(text) {
  const words = text.replace(/[#*]\s*\w*\d\w*/g, ' ').replace(/\d{3,}/g, ' ')
    .replace(/\b(POS|PURCHASE|INTERAC|DEBIT|VISA|MC|APOS|OPOS|IDP|FPOS|RETAIL)\b/gi, ' ')
    .split(/\s+/).filter((w) => w.length > 1)
  return words.slice(0, 2).join(' ').toLowerCase()
}

export default function RuleDialog({ rule, suggestFrom, categories, accounts, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState(() => rule ? { ...rule } : {
    name: '', priority: 100, match_field: 'description', match_type: 'contains',
    pattern: suggestFrom ? suggestPattern(suggestFrom.tx.description) : '',
    amount_min: null, amount_max: null, account_id: null,
    set_category_id: suggestFrom?.category_id ?? null, set_payee: '', is_active: true,
  })
  const [apply, setApply] = useState(true)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const body = () => ({ ...f, amount_min: f.amount_min === '' ? null : f.amount_min, amount_max: f.amount_max === '' ? null : f.amount_max,
    account_id: f.account_id ? Number(f.account_id) : null, set_payee: f.set_payee || null, priority: Number(f.priority) || 100 })

  useEffect(() => {
    if (!f.pattern) { setPreview(null); return }
    const timer = setTimeout(() => api.post('/rules/test', body()).then(setPreview).catch(() => setPreview(null)), 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.pattern, f.match_type, f.match_field, f.amount_min, f.amount_max, f.account_id])

  const save = async () => {
    setBusy(true)
    try {
      const r = rule?.id ? await api.patch(`/rules/${rule.id}`, body()) : await api.post(`/rules${apply ? '?apply=true' : ''}`, body())
      toast(rule?.id ? t('Rule updated') : t('Rule created'))
      onSaved(r)
      onClose()
    } catch (e) { toast(e.message, 'error') }
    setBusy(false)
  }

  return (
    <Dialog wide title={rule?.id ? t('Edit rule') : t('New categorization rule')} onClose={onClose} footer={<>
      {!rule?.id && <label className="check" style={{ marginRight: 'auto' }}><input type="checkbox" checked={apply} onChange={(e) => setApply(e.target.checked)} />{t('Also apply to uncategorized transactions')}</label>}
      <button className="btn" onClick={onClose}>{t('Cancel')}</button>
      <button className="btn primary" onClick={save} disabled={busy || !f.pattern || (!f.set_category_id && !f.set_payee)}>{t('Save rule')}</button>
    </>}>
      <div className="form-grid">
        <Field label={t('When the')}><select className="input" value={f.match_field} onChange={set('match_field')}>
          <option value="description">{t('description')}</option><option value="payee">{t('payee')}</option></select></Field>
        <Field label="…"><select className="input" value={f.match_type} onChange={set('match_type')}>
          <option value="contains">{t('contains')}</option><option value="starts_with">{t('starts with')}</option><option value="equals">{t('is exactly')}</option><option value="regex">{t('matches pattern (regex)')}</option></select></Field>
        <Field label={t('Text')} className="full" hint={t('Not case-sensitive. Keep it short, e.g. “loblaws” or “netflix”.')}><input className="input" autoFocus value={f.pattern} onChange={set('pattern')} /></Field>
        <Field label={t('Set category')}><CategorySelect categories={categories} value={f.set_category_id} onChange={(v) => setF({ ...f, set_category_id: v })} placeholder={t("Don't change")} /></Field>
        <Field label={t('Rename payee to')} hint={t('Optional')}><input className="input" value={f.set_payee ?? ''} onChange={set('set_payee')} placeholder={t('e.g. Loblaws')} /></Field>
        <Field label={t('Only for account')}><select className="input" value={f.account_id ?? ''} onChange={set('account_id')}>
          <option value="">{t('Any account')}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label={t('Priority')} hint={t('Lower numbers win when several rules match.')}><input className="input" type="number" value={f.priority} onChange={set('priority')} /></Field>
        <Field label={t('Amount from')} hint={t('Signed: money out is negative.')}><input className="input" type="number" step="0.01" value={f.amount_min ?? ''} onChange={set('amount_min')} /></Field>
        <Field label={t('Amount to')}><input className="input" type="number" step="0.01" value={f.amount_max ?? ''} onChange={set('amount_max')} /></Field>
      </div>
      {preview && (
        <div style={{ marginTop: 18 }}>
          <div className="strong small" style={{ marginBottom: 8 }}>{preview.count === 1 ? t('Matches 1 existing transaction') : t('Matches {n} existing transactions', { n: preview.count })}</div>
          <div className="list card" style={{ boxShadow: 'none' }}>
            {preview.examples.slice(0, 5).map((e, i) => (
              <div key={i} className="list-row" style={{ padding: '8px 14px' }}>
                <span className="muted small num" style={{ width: 90 }}>{date(e.date)}</span>
                <span className="grow title small">{e.description}</span>
                <span className="small num">{money(e.amount)}</span>
              </div>
            ))}
            {preview.count === 0 && <div className="list-row muted small">{t('Nothing yet; the rule will apply to future imports.')}</div>}
          </div>
        </div>
      )}
    </Dialog>
  )
}
