import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Loader2, SendHorizontal } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Empty, Loading, PageHead, useData } from '../components/ui'
import { t } from '../i18n'

const STARTERS = [
  'How much did we spend on groceries in the last 3 months?',
  'Which subscriptions am I paying for?',
  'Am I on track with my budgets this month?',
  'What were my biggest expenses last month?',
]

export default function Chat() {
  const { user } = useApp()
  const status = useData(() => api.get('/ai/status'), [user.ai_opt_in])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const logRef = useRef(null)
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, busy])

  if (!status.data) return <Loading />
  const st = status.data
  if (!st.available) return <><PageHead title={t('Ask AI')} /><div className="card"><Empty icon={Bot} title={t('AI chat is turned off')}>{t('An admin can enable a household model or let members connect their own ChatGPT (OpenAI) account.')}</Empty></div></>
  if (!st.ready) return <><PageHead title={t('Ask AI')} /><div className="card"><Empty icon={Bot} title={t('Set up AI chat for your account')} action={<Link to="/settings#ai" className="btn primary">{t('Open settings')}</Link>}>
    {t('Choose the household model or connect your own ChatGPT (OpenAI) account, then allow it to read your accounts, budgets and recent transactions when you ask a question.')}</Empty></div></>

  const send = async (text) => {
    const next = [...messages, { role: 'user', content: text }]
    setMessages(next); setInput(''); setBusy(true); setError('')
    try {
      const r = await api.post('/ai/chat', { messages: next })
      setMessages([...next, { role: 'assistant', content: r.reply }])
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  return (
    <>
      <PageHead title={t('Ask AI')} sub={st.provider === 'openai' ? t('Answers come from {model} on your OpenAI account, using your own data. It can be wrong; check the numbers that matter.', { model: st.model }) : t('Answers come from {model}, using your own data. It can be wrong; check the numbers that matter.', { model: st.model })} />
      <section className="card chat">
        <div className="chat-log" ref={logRef}>
          {messages.length === 0 && (
            <div className="empty" style={{ margin: 'auto' }}>
              <span className="tile"><Bot /></span>
              <h3>{t('Ask about your money')}</h3>
              <div className="row wrap" style={{ justifyContent: 'center', gap: 8, marginTop: 8 }}>
                {STARTERS.map((s) => <button key={s} className="btn sm" onClick={() => send(t(s))}>{t(s)}</button>)}
              </div>
            </div>
          )}
          {messages.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.content}</div>)}
          {busy && <div className="msg assistant row muted"><Loader2 size={15} className="spin" />{t('Thinking…')}</div>}
          {error && <div className="error-text">{error}</div>}
        </div>
        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); input.trim() && send(input.trim()) }}>
          <input className="input" placeholder={t('Ask a question about your finances…')} value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} aria-label={t('Message')} />
          <button className="btn primary" disabled={busy || !input.trim()} aria-label={t('Send')}><SendHorizontal /></button>
        </form>
      </section>
    </>
  )
}
