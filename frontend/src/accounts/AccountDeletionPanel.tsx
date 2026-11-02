import { useState, type FormEvent } from 'react'
import { request } from '../api'
import { clearGoals } from '../goals/goalStorage'
import './account-deletion.css'

const confirmationText = 'EXCLUIR MINHA CONTA'

type Props = {
  identity: string
  reauthenticate: (password: string) => Promise<{ access_token: string }>
  onDeleted: (goalsCleared: boolean) => Promise<void>
}

export function AccountDeletionPanel({ identity, reauthenticate, onDeleted }: Props) {
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || confirmation !== confirmationText || !password) return
    setBusy(true); setError('')
    try {
      const freshSession = await reauthenticate(password)
      setPassword('')
      const result = await request<{ status: string }>('account/delete', freshSession.access_token, {
        method: 'POST', body: JSON.stringify({ confirmation: confirmationText }),
      })
      if (result.status !== 'deleted') throw new Error('A exclusão não foi concluída. Tente novamente.')
      const goalsCleared = clearGoals(identity)
      await onDeleted(goalsCleared)
    } catch (cause) {
      setPassword('')
      setError((cause as Error).message || 'A exclusão foi interrompida com segurança. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  return <details className="account-deletion">
    <summary>Excluir minha conta</summary>
    <div className="account-deletion-body">
      <p>Esta ação remove permanentemente sua carteira, observações, convites e identidade Supabase. A exclusão não pode ser desfeita.</p>
      <form onSubmit={event => { void submit(event) }}>
        <label>Confirme sua senha
          <input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required disabled={busy}/>
        </label>
        <label>Digite <strong>{confirmationText}</strong>
          <input value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off" required disabled={busy}/>
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy || confirmation !== confirmationText || !password}>
          {busy ? 'Excluindo conta…' : 'Excluir permanentemente'}
        </button>
      </form>
    </div>
  </details>
}
