import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, Eye, EyeOff, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getSupabase } from './supabase'
import { apiBase } from '../runtime'
import { Button } from '../components/ui/button'
import './login.css'
import './invite-password.css'

type Eligibility = 'checking' | 'eligible' | 'denied'

export function InvitePasswordPage({ invitationId, token, onComplete }: { invitationId: string; token: string; onComplete: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [visible, setVisible] = useState(false)
  const [confirmVisible, setConfirmVisible] = useState(false)
  const [eligibility, setEligibility] = useState<Eligibility>('checking')
  const [passwordSaved, setPasswordSaved] = useState(false)
  const submissionInFlight = useRef(false)
  const claim = useRef('')

  useEffect(() => {
    let active = true
    if (!invitationId || !token) { setEligibility('denied'); return }
    void fetch(`${apiBase()}/api/account/invitations/${encodeURIComponent(invitationId)}/eligibility`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(response => {
      if (active) setEligibility(response.ok ? 'eligible' : 'denied')
    }).catch(() => { if (active) setEligibility('denied') })
    return () => { active = false }
  }, [invitationId, token])

  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (submissionInFlight.current || eligibility !== 'eligible') return
    if (!passwordSaved && (password.length < 12 || password !== confirm)) { setError('Use ao menos 12 caracteres e repita a mesma senha.'); return }
    submissionInFlight.current = true
    setBusy(true)
    let updatedPassword = passwordSaved
    try {
      const client = getSupabase()
      if (!client) throw new Error('Autenticação indisponível.')
      const currentSession = await client.auth.getSession()
      const currentToken = currentSession.data.session?.access_token
      if (currentSession.error || !currentToken) throw new Error('A sessão do convite expirou. Abra um novo link enviado pelo administrador.')
      if (!claim.current) {
        const claimResponse = await fetch(`${apiBase()}/api/account/invitations/${encodeURIComponent(invitationId)}/claim`, {
          method: 'POST', headers: { Authorization: `Bearer ${currentToken}` },
        })
        if (!claimResponse.ok) throw new Error('Este convite não está mais disponível. Solicite um novo ao administrador.')
        claim.current = (await claimResponse.json() as { claim_token: string }).claim_token
        if (!claim.current) throw new Error('Não foi possível reservar este convite. Tente novamente.')
      }
      if (!updatedPassword) {
        const { error: updateError } = await client.auth.updateUser({ password })
        if (updateError) throw new Error('Não foi possível definir a senha. O convite continua protegido; tente novamente ou solicite ajuda ao administrador.')
        updatedPassword = true; setPasswordSaved(true); setPassword(''); setConfirm('')
      }
      const refreshed = await client.auth.getSession()
      const activationToken = refreshed.data.session?.access_token
      if (refreshed.error || !activationToken) throw new Error('Sua senha foi salva, mas a sessão expirou antes da confirmação do acesso. Entre novamente ou solicite ajuda ao administrador.')
      const activation = await fetch(`${apiBase()}/api/account/activate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${activationToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ invitation_id: invitationId, claim_token: claim.current }),
      })
      if (!activation.ok) throw new Error(activation.status >= 500
        ? 'Sua senha foi salva, mas não foi possível confirmar a ativação. Tente confirmar o acesso novamente.'
        : 'A autorização expirou ou foi revogada. O acesso não foi confirmado; solicite ajuda ao administrador.')
      setPassword(''); setConfirm(''); onComplete()
    } catch (cause) {
      // Once the password is saved, retry the same activation: its response may have been lost.
      if (claim.current && !updatedPassword) {
        await fetch(`${apiBase()}/api/account/invitations/${encodeURIComponent(invitationId)}/claim`, {
          method: 'DELETE', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ claim_token: claim.current }),
        }).catch(() => undefined)
        claim.current = ''
      }
      setError(cause instanceof TypeError && updatedPassword
        ? 'Sua senha foi salva, mas a conexão terminou antes da confirmação. Tente confirmar o acesso novamente.'
        : (cause as Error).message || 'Não foi possível concluir a ativação.')
    } finally { submissionInFlight.current = false; setBusy(false) }
  }

  return <main className="invite-page">
    <section className="invite-card" aria-labelledby="invite-title">
      <div className="invite-icon"><ShieldCheck size={23}/></div>
      <p className="login-eyebrow">ACESSO CONCEDIDO PELO ADMINISTRADOR</p>
      <h1 id="invite-title">Ative sua conta</h1>
      <p className="invite-description">Defina uma senha pessoal para concluir este convite.</p>
      {eligibility === 'checking' && <p className="invite-status" role="status"><LoaderCircle className="spin" size={16}/> Validando convite…</p>}
      {eligibility === 'denied' && <div className="login-error" role="alert">Este link não corresponde a um convite atual, válido e autorizado para esta conta. Solicite novo acesso ao administrador.</div>}
      {eligibility === 'eligible' && <form onSubmit={submit} className="invite-form">
        {passwordSaved ? <p role="status">Sua senha foi salva. Confirme a ativação para concluir seu acesso.</p> : <>
        <label htmlFor="invite-password">Nova senha<span className="password-field"><LockKeyhole size={17}/><input id="invite-password" type={visible ? 'text' : 'password'} autoComplete="new-password" minLength={12} required value={password} disabled={busy} onChange={event => setPassword(event.target.value)}/><button type="button" aria-label={visible ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={visible} onClick={() => setVisible(value => !value)}><span className="sr-only">{visible ? 'Ocultar senha' : 'Mostrar senha'}</span>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></span></label>
        <label htmlFor="invite-password-confirm">Confirme a senha<span className="password-field"><LockKeyhole size={17}/><input id="invite-password-confirm" type={confirmVisible ? 'text' : 'password'} autoComplete="new-password" minLength={12} required value={confirm} disabled={busy} onChange={event => setConfirm(event.target.value)}/><button type="button" aria-label={confirmVisible ? 'Ocultar confirmação de senha' : 'Mostrar confirmação de senha'} aria-pressed={confirmVisible} onClick={() => setConfirmVisible(value => !value)}><span className="sr-only">{confirmVisible ? 'Ocultar confirmação de senha' : 'Mostrar confirmação de senha'}</span>{confirmVisible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></span></label>
        </>}
        {error && <p role="alert" className="login-error">{error}</p>}
        <Button type="submit" disabled={busy} className="login-submit">{busy ? <><LoaderCircle size={17} className="spin"/> Ativando…</> : passwordSaved ? 'Confirmar ativação do acesso' : 'Definir senha e ativar acesso'}</Button>
      </form>}
      <Link to="/login" className="invite-back"><ArrowLeft size={15}/> Voltar ao login</Link>
    </section>
  </main>
}
