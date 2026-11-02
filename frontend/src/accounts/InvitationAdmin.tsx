import { useEffect, useState, type FormEvent } from 'react'
import { apiBase } from '../runtime'

type Invitation = { id: string; email: string; expires_at: string; accepted: boolean; revoked: boolean }

export function InvitationAdmin({ token }: { token: string }) {
  const [items, setItems] = useState<Invitation[]>([])
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const endpoint = `${apiBase()}/api/admin/invitations`
  async function load() {
    const response = await fetch(endpoint, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Não foi possível carregar os convites.')
    setItems(await response.json())
  }
  useEffect(() => { void load().catch(() => setError('Não foi possível carregar os convites.')) }, [token])
  async function create(event: FormEvent) {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(endpoint, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ email, expires_in_days: 7 }) })
      if (!response.ok) throw new Error('Não foi possível enviar o convite. Verifique o limite e a configuração do Supabase.')
      setEmail(''); await load()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  async function revoke(id: string) {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${endpoint}/${encodeURIComponent(id)}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('Não foi possível revogar o convite/acesso.')
      await load()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  return <details className="panel account-invitation-admin"><summary>Administração de convites</summary>
    <form onSubmit={create}><label htmlFor="invite-email">E-mail para convite</label><input id="invite-email" type="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/><button type="submit" disabled={busy}>{busy ? 'Processando…' : 'Enviar convite (7 dias)'}</button></form>
    {error && <p role="alert">{error}</p>}
    <ul>{items.map(item => <li key={item.id}><span>{item.email} · {item.revoked ? 'revogado' : item.accepted ? 'ativo' : `expira ${new Date(item.expires_at).toLocaleDateString('pt-BR')}`}</span>{!item.revoked && <button type="button" disabled={busy} onClick={() => void revoke(item.id)}>{item.accepted ? 'Revogar acesso' : 'Revogar convite'}</button>}</li>)}</ul>
  </details>
}
