import { useState } from 'react'
import { ArrowRight, Check, X } from 'lucide-react'
import { api } from '../api'
import { t } from '../i18n'
import { Dialog, Money, useToast } from './ui'
import { date } from '../lib/format'

export default function TransferReview({ pairs, onClose, onDone }) {
  const toast = useToast()
  const [skipped, setSkipped] = useState(new Set())
  const [done, setDone] = useState(new Set())
  const open = pairs.filter((p) => !skipped.has(p.out.id) && !done.has(p.out.id))
  const match = async (p) => {
    try { await api.post('/transfers/match', { out_id: p.out.id, in_id: p.in.id }); setDone((s) => new Set(s).add(p.out.id)); onDone() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog wide title={t('Transfers between your accounts')} onClose={onClose} footer={<button className="btn primary" onClick={onClose}>{t('Done')}</button>}>
      <p className="small muted" style={{ marginBottom: 14 }}>{t('Each pair looks like money moving between two of your own accounts. Matching them marks both as a transfer, so neither counts as spending or income.')}</p>
      {open.length === 0 ? <p className="strong">{t('Nothing left to review.')}</p> : (
        <div className="list card" style={{ boxShadow: 'none' }}>
          {open.map((p) => (
            <div key={p.out.id} className="list-row" style={{ flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                <div className="title">{p.out.description}</div>
                <div className="meta">{p.out.account_name} · {date(p.out.date)}</div>
              </div>
              <Money value={p.out.amount} currency={p.out.currency} className="expense strong" />
              <ArrowRight size={16} className="muted" />
              <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                <div className="title">{p.in.description}</div>
                <div className="meta">{p.in.account_name} · {date(p.in.date)}</div>
              </div>
              <Money value={p.in.amount} currency={p.in.currency} className="income strong" />
              <div className="row" style={{ gap: 4 }}>
                <button className="btn sm primary" onClick={() => match(p)}><Check />{t('Match')}</button>
                <button className="btn sm ghost" onClick={() => setSkipped((s) => new Set(s).add(p.out.id))}><X />{t('Not a transfer')}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Dialog>
  )
}
