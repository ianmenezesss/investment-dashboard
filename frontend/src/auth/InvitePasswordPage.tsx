import { useState, type FormEvent } from 'react'
import { getSupabase } from './supabase'
import { Button } from '../components/ui/button'

export function InvitePasswordPage({ onComplete }: { onComplete: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    if (password.length < 12 || password !== confirm) { setError('Use ao menos 12 caracteres e repita a mesma senha.'); return }
    setBusy(true)
    try {
      const client = getSupabase()
      if (!client) throw new Error('Autenticação indisponível.')
      const { error: updateError } = await client.auth.updateUser({ password })
      if (updateError) throw new Error('Não foi possível definir a senha. Reabra o convite ou solicite outro ao administrador.')
      setPassword(''); setConfirm(''); onComplete()
    } catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
  }
  return <main className="session-gate"><section className="login-card"><h1>Ative sua conta</h1><p>Defina uma senha pessoal para concluir o convite.</p><form onSubmit={submit}>
    <label htmlFor="invite-password">Nova senha<input id="invite-password" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={event => setPassword(event.target.value)}/></label>
    <label htmlFor="invite-password-confirm">Confirme a senha<input id="invite-password-confirm" type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={event => setConfirm(event.target.value)}/></label>
    {error && <p role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Definir senha e continuar'}</Button>
  </form></section></main>
}
