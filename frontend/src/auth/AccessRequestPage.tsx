import { useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, ChartNoAxesCombined, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { apiBase } from '../runtime'
import './login.css'

const neutralResponse = 'Se sua solicitação puder ser processada, ela será analisada. Caso seja aprovada, você receberá um convite por e-mail.'

export function AccessRequestPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const submissionInFlight = useRef(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submissionInFlight.current || submitted) return
    submissionInFlight.current = true
    setBusy(true); setError('')
    try {
      const response = await fetch(`${apiBase()}/api/access-requests`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      if (!response.ok) throw new Error('request_failed')
      setSubmitted(true)
    } catch {
      submissionInFlight.current = false
      setError('Não foi possível enviar agora. Tente novamente mais tarde.')
    } finally { setBusy(false) }
  }

  return <div className="login-page access-request-page">
    <section className="login-story" aria-label="Investment Dashboard">
      <Link className="brand login-brand" to="/login"><span className="brand-icon"><ChartNoAxesCombined size={28}/></span>investment<span className="brand-dot">.</span></Link>
      <div className="login-story-content"><span className="login-kicker"><span/> UM ESPAÇO PRIVADO</span><h1>Conheça a plataforma.<br/><em>Com acesso seguro.</em></h1><p>As solicitações são analisadas pelo administrador. Nenhuma conta é criada automaticamente.</p></div>
      <div className="login-principles"><span><ShieldCheck size={17}/> Aprovação manual</span><span>7 dias de acesso</span></div>
    </section>
    <main className="login-main"><div className="login-card"><div className="login-lock"><ShieldCheck size={24}/></div><p className="login-eyebrow">SOLICITAÇÃO DE ACESSO</p><h2>Peça uma conta de teste.</h2><p className="login-description">Informe seu e-mail. Não pediremos senha nem informações financeiras.</p>
      {submitted ? <div className="access-request-success" role="status">{neutralResponse}</div> : <form className="access-request-form" onSubmit={event => { void submit(event) }}>
        <label htmlFor="access-request-email">E-mail<input id="access-request-email" type="email" autoComplete="email" maxLength={320} required value={email} disabled={busy} onChange={event => setEmail(event.target.value)}/></label>
        {error && <p className="access-request-error" role="alert">{error}</p>}
        <Button type="submit" className="login-submit" disabled={busy}>{busy ? 'Enviando…' : 'Enviar solicitação'} <ArrowRight size={17}/></Button>
      </form>}
      <Link className="access-request-back" to="/login"><ArrowLeft size={14}/> Voltar ao login</Link>
    </div><footer className="login-footer"><ShieldCheck size={13}/> Seu patrimônio é pessoal. Seu acesso também.</footer></main>
  </div>
}
