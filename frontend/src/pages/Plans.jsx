import { useState } from 'react'
import { AlertTriangle, ChevronDown, Info, Landmark, Plus, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { t } from '../i18n'
import { Confirm, Dialog, Empty, Field, Loading, Money, PageHead, Progress, useData, useToast } from '../components/ui'
import { date, money, todayISO } from '../lib/format'
import { PLAN_MOVES } from '../lib/registered'

const KIND_HELP = {
  tfsa: () => t('Your TFSA room for the year is shown in CRA My Account under "RRSP and TFSA". Withdrawals are added back to your room on January 1 of the next year.'),
  rrsp: () => t('Use the RRSP deduction limit from your latest Notice of Assessment or CRA My Account. The rules allow a $2,000 cumulative over-contribution before a penalty applies.'),
  fhsa: () => t('Use your FHSA participation room from CRA My Account. The annual and lifetime limits set by CRA apply; unused room can carry forward within those limits.'),
}

const cad = (v) => money(v, 'CAD')

function warningText(w) {
  const amount = cad(w.amount)
  switch (w.code) {
    case 'rrsp_over_buffer': return t('Over your deduction limit by more than the $2,000 buffer ({amount} past it). A 1% monthly tax can apply to the excess.', { amount })
    case 'rrsp_in_buffer': return t('{amount} over your deduction limit, but still inside the $2,000 over-contribution buffer.', { amount })
    case 'over_room': return t('Contributions are {amount} over the room you entered. Over-contributions can be taxed at 1% per month until removed.', { amount })
    case 'tfsa_withdrawn': return t("{amount} withdrawn this year comes back as room on January 1, {year}, not this year. Re-contributing it now uses this year's room.", { amount, year: w.year })
    case 'fhsa_withdrawn': return t("{amount} withdrawn this year. FHSA withdrawals don't give room back, including qualifying withdrawals for a first home.", { amount })
    default: return w.code
  }
}

// The next year's room, written from the server's codes and numbers. Always an estimate.
function estimateText(e) {
  switch (e.code) {
    case 'tfsa_next': return t('Unused room {unused} + withdrawals this year {withdrawn} + the {year} limit {limit}.', { unused: cad(e.unused), withdrawn: cad(e.withdrawn), year: e.year, limit: cad(e.limit) })
    case 'tfsa_next_partial': return t('Unused room {unused} + withdrawals this year {withdrawn}, so far. The {year} limit is announced each fall; it adds to this.', { unused: cad(e.unused), withdrawn: cad(e.withdrawn), year: e.year })
    case 'fhsa_next': return t('{annual} for {year} plus {carry} of unused room carried forward (at most {annual}), within the {lifetime} lifetime limit ({left} of it left).', { annual: cad(8000), year: e.year, carry: cad(e.carry), lifetime: cad(40000), left: cad(e.lifetime_left) })
    default: return ''
  }
}

export default function Plans() {
  const { version, bump } = useApp()
  const plans = useData(() => api.get('/plans'), [version])
  const accounts = useData(() => api.get('/accounts'), [version])
  const [editing, setEditing] = useState(null)
  const [adding, setAdding] = useState(null)
  const [confirm, setConfirm] = useState(null)
  if (!plans.data) return <Loading />
  const years = [...new Set(plans.data.map((p) => p.year))].sort((a, b) => b - a)
  const accts = accounts.data?.items ?? []

  return (
    <>
      <PageHead title={t('Registered accounts')} sub={t('Track TFSA, RRSP and FHSA contributions against the room CRA gives you. Copy the room from CRA My Account; FinVault does the counting.')}>
        <button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add room for a year')}</button>
      </PageHead>
      <div className="banner plan-note" style={{ marginBottom: 20 }}>
        <Info />
        <div className="banner-body">{t('These are reminders to help you stay inside your limits, not tax advice. CRA\'s numbers always win, so check My Account before a big contribution.')}</div>
      </div>
      {plans.data.length === 0 ? (
        <div className="card"><Empty icon={Landmark} title={t('No registered accounts yet')} action={<button className="btn primary" onClick={() => setEditing({})}><Plus />{t('Add room for a year')}</button>}>
          {t('Add this year\'s TFSA, RRSP or FHSA room. Link the matching account and deposits are counted automatically.')}
          {' '}{t('Or mark an account as a TFSA, FHSA or RRSP and import its statements: each year is set up for you.')}
        </Empty></div>
      ) : years.map((y) => (
        <section key={y} style={{ marginBottom: 24 }} aria-labelledby={`plans-${y}`}>
          <h2 id={`plans-${y}`} style={{ marginBottom: 12 }}>{y}</h2>
          <div className="grid-3">
            {plans.data.filter((p) => p.year === y).map((p) => (
              <PlanCard key={p.id} p={p} onEdit={() => setEditing(p)} onAdd={() => setAdding(p)}
                onDelete={() => setConfirm({ title: t('Delete {kind} {year}?', { kind: t(p.label), year: p.year }), body: t('Only FinVault\'s record is removed.'), onConfirm: async () => { await api.del(`/plans/${p.id}`); bump() } })}
                onDeleteEntry={async (e) => { await api.del(`/plans/${p.id}/entries/${e.id}`); bump() }} />
            ))}
          </div>
        </section>
      ))}
      {editing && <PlanDialog plan={editing} accounts={accts} onClose={() => setEditing(null)} onSaved={bump} />}
      {adding && <EntryDialog plan={adding} onClose={() => setAdding(null)} onSaved={bump} />}
      {confirm && <Confirm {...confirm} onClose={() => setConfirm(null)} />}
    </>
  )
}

function PlanCard({ p, onEdit, onAdd, onDelete, onDeleteEntry }) {
  const moves = PLAN_MOVES()
  const linked = p.accounts.map((a) => a.name).filter(Boolean)
  const b = p.by_type
  const rows = [
    [t('Contributed'), b.contribution, true],
    [t('RRSP to FHSA'), b.rrsp_to_fhsa, p.kind === 'fhsa' || b.rrsp_to_fhsa > 0],
    [t('Withdrawn'), b.withdrawal, true],
    [t('Transferred in'), b.transfer_in, true],
    [t('Transferred out'), b.transfer_out, true],
    [t('Growth'), b.growth, true],
    [t('Fees'), b.fee, b.fee > 0],
  ].filter((r) => r[2])
  const quiet = (p.lines.trade ?? 0) + (p.lines.other ?? 0)
  const est = p.estimate
  return (
    <article className="card plan-card" aria-labelledby={`plan-${p.id}`}>
      <div className="card-head">
        <div>
          <h3 id={`plan-${p.id}`} className="plan-title">{t(p.label)} {p.year}</h3>
          <div className="sub">{linked.length ? t('Counts lines from {names}', { names: linked.join(', ') }) : t('Entries added by hand')}</div>
        </div>
        <div className="row" style={{ gap: 0 }}>
          <button className="btn sm ghost" onClick={onEdit} aria-label={t('Edit {kind} {year}', { kind: t(p.label), year: p.year })}>{t('Edit')}</button>
          <button className="icon-btn" aria-label={t('Delete {kind} {year}', { kind: t(p.label), year: p.year })} onClick={onDelete}><Trash2 /></button>
        </div>
      </div>
      <div className="card-body stack" style={{ gap: 12 }}>
        {p.room_set ? (
          <>
            <div className="row" style={{ alignItems: 'baseline' }}>
              <div style={{ fontSize: 24, fontWeight: 700 }} className={p.remaining < 0 ? 'expense' : ''}><Money value={p.remaining} currency="CAD" /></div>
              <span className="muted small">{p.remaining < 0 ? t('over your room') : t('room left')}</span>
            </div>
            <Progress thick value={p.percent} color={p.remaining < 0 ? 'var(--red)' : p.percent >= 90 ? 'var(--ink-2)' : 'var(--green)'} />
            <div className="row small muted" style={{ justifyContent: 'space-between' }}>
              <span>{t('Room')} <Money value={p.room} currency="CAD" /></span>
              <span>{t('Used')} <Money value={p.contributed} currency="CAD" /></span>
            </div>
          </>
        ) : (
          <div className="plan-room-missing">
            <p className="strong">{t('Room not entered yet')}</p>
            <p className="small muted">{t('Copy your {kind} room for {year} from CRA My Account to see what is left. {used} counted so far.', { kind: t(p.label), year: p.year, used: cad(p.contributed) })}</p>
            <button className="btn primary sm" onClick={onEdit}>{t('Enter CRA room')}</button>
          </div>
        )}

        <dl className="plan-types" aria-label={t('By type')}>
          {rows.map(([label, value]) => (
            <div key={label}><dt>{label}</dt><dd><Money value={value} currency="CAD" /></dd></div>
          ))}
        </dl>
        {quiet > 0 && <p className="small muted">{quiet === 1 ? t('1 trade or other line doesn\'t use room.') : t('{n} trades and other lines don\'t use room.', { n: quiet })}</p>}
        {p.untyped > 0 && <p className="small muted">{p.untyped === 1 ? t('1 line has no type yet: money in counts as a contribution, money out as a withdrawal.') : t('{n} lines have no type yet: money in counts as a contribution, money out as a withdrawal.', { n: p.untyped })}</p>}

        {p.warnings.filter((w) => w.code !== 'needs_room').map((w) => (
          <div key={w.code} className={`banner ${w.level === 'danger' ? 'plan-danger' : 'plan-note'}`}>
            <AlertTriangle /><div className="banner-body small">{warningText(w)}</div>
          </div>
        ))}

        {est && (
          <div className="plan-estimate">
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
              <span className="strong">{t('{year} room', { year: est.year })} <span className="pill">{t('Estimate')}</span></span>
              {est.amount != null && <span className="plan-estimate-figure"><Money value={est.amount} currency="CAD" />{est.code === 'tfsa_next_partial' && <span className="small muted"> {t('+ new limit')}</span>}</span>}
            </div>
            {est.code === 'needs_room' && <p className="small muted">{t('Enter this year\'s room to see an estimate for {year}.', { year: est.year })}</p>}
            {est.code === 'fhsa_closed' && <p className="small muted">{t('Your first FHSA was opened in {opened}, so it must close by the end of {close}. There is no FHSA room for {year}.', { opened: est.opened, close: est.close_year, year: est.year })}</p>}
            {estimateText(est) && <p className="small muted">{estimateText(est)}</p>}
            {est.closing_soon && <p className="small muted">{t('Your FHSA must close by the end of {close}, 15 years after you opened your first one in {opened}. Unused money can move to an RRSP without using RRSP room.', { close: est.close_year, opened: est.opened })}</p>}
            <p className="small muted">{t('An estimate from the lines FinVault has seen. CRA\'s figure always wins.')}</p>
          </div>
        )}
        {p.kind === 'rrsp' && <p className="small muted">{t('No estimate for next year\'s RRSP room: it depends on your earned income and comes on your Notice of Assessment.')}</p>}

        <details className="entries">
          <summary className="small strong">{t(p.entries.length === 1 ? '{n} entry' : '{n} entries', { n: p.entries.length })}<ChevronDown aria-hidden="true" /></summary>
          <div className="list" style={{ marginTop: 8 }}>
            {p.entries.map((e) => (
              <div key={e.id} className="row small" style={{ padding: '6px 0' }}>
                <span className="grow plan-entry">
                  <span className="plan-entry-note">{e.note || moves[e.move]}</span>
                  <span className="plan-entry-move">{[date(e.date), e.note && e.note !== moves[e.move] ? moves[e.move] : null].filter(Boolean).join(' · ')}</span>
                </span>
                <Money value={e.amount} currency="CAD" sign colored />
                {e.source === 'manual' && <button className="icon-btn" aria-label={t('Delete')} onClick={() => onDeleteEntry(e)}><Trash2 size={14} /></button>}
              </div>
            ))}
          </div>
        </details>
        <button className="btn sm" onClick={onAdd}><Plus />{t('Add contribution or withdrawal')}</button>
      </div>
    </article>
  )
}

function PlanDialog({ plan, accounts, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ kind: plan.kind ?? 'tfsa', year: plan.year ?? new Date().getFullYear(), room: plan.room ?? '', account_id: plan.account_id ?? '', notes: plan.notes ?? '' })
  const save = async () => {
    const body = { ...f, year: Number(f.year), room: f.room === '' ? null : Number(f.room), account_id: f.account_id ? Number(f.account_id) : null }
    try { plan.id ? await api.patch(`/plans/${plan.id}`, body) : await api.post('/plans', body); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={plan.id ? t('Edit room') : t('Add room for a year')} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save}>{t('Save')}</button></>}>
      <div className="form-grid">
        <Field label={t('Plan')}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="tfsa">{t('TFSA')}</option><option value="rrsp">{t('RRSP')}</option><option value="fhsa">{t('FHSA')}</option></select></Field>
        <Field label={t('Tax year')}><input className="input" type="number" value={f.year} onChange={(e) => setF({ ...f, year: e.target.value })} /></Field>
        <Field label={t('Room from CRA')} className="full" hint={`${KIND_HELP[f.kind]()} ${t('Leave it empty if you don\'t have the figure yet.')}`}><input className="input" type="number" min="0" step="0.01" value={f.room ?? ''} onChange={(e) => setF({ ...f, room: e.target.value })} /></Field>
        <Field label={t('Linked account')} className="full" hint={t('Deposits into this account count as contributions and withdrawals are subtracted. Lines categorized as income (interest, dividends) are ignored.')}>
          <select className="input" value={f.account_id} onChange={(e) => setF({ ...f, account_id: e.target.value })}><option value="">{t('None, I\'ll add entries by hand')}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        </Field>
        <Field label={t('Notes')} className="full"><input className="input" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
    </Dialog>
  )
}

function EntryDialog({ plan, onClose, onSaved }) {
  const toast = useToast()
  const [kind, setKind] = useState('in')
  const [f, setF] = useState({ date: todayISO().slice(0, 4) === String(plan.year) ? todayISO() : `${plan.year}-01-01`, amount: '', note: '' })
  const save = async () => {
    try { await api.post(`/plans/${plan.id}/entries`, { ...f, amount: (kind === 'in' ? 1 : -1) * Number(f.amount) }); onSaved(); onClose() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Dialog title={`${t(plan.label)} ${plan.year}`} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t('Cancel')}</button><button className="btn primary" onClick={save} disabled={!f.amount}>{t('Add')}</button></>}>
      <div className="form-grid">
        <div className="full segmented" style={{ width: 'fit-content' }}>
          <button aria-pressed={kind === 'in'} className={kind === 'in' ? 'on' : ''} onClick={() => setKind('in')}>{t('Contribution')}</button>
          <button aria-pressed={kind === 'out'} className={kind === 'out' ? 'on' : ''} onClick={() => setKind('out')}>{t('Withdrawal')}</button>
        </div>
        <Field label={t('Amount')}><input className="input" type="number" min="0" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label={t('Date')}><input className="input" type="date" min={`${plan.year}-01-01`} max={`${plan.year}-12-31`} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field label={t('Note')} className="full"><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder={t('e.g. at another bank')} /></Field>
      </div>
    </Dialog>
  )
}
