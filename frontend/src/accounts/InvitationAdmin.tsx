import { useEffect, useState, type FormEvent } from 'react'
import { apiBase } from '../runtime'

type Invitation = { id: string; email: string; expires_at: string; accepted: boolean; revoked: boolean }
type AccessRequest = { id: string; email: string; requested_at: string; status: 'pending' | 'approved' | 'rejected'; processing?: boolean }

export function InvitationAdmin({ token }: { token: string }) {
  const [items, setItems] = useState<Invitation[]>([])
  const [requests, setRequests] = useState<AccessRequest[]>([])
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const endpoint = `${apiBase()}/api/admin/invitations`
  const requestsEndpoint = `${apiBase()}/api/admin/access-requests`
  async function load() {
    const response = await fetch(endpoint, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Não foi possível carregar os convites.')
    setItems(await response.json())
  }
  async function loadRequests() {
    const response = await fetch(requestsEndpoint, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Não foi possível carregar as solicitações.')
    setRequests(await response.json())
  }
  useEffect(() => { void Promise.all([load(), loadRequests()]).catch(() => setError('Não foi possível carregar os dados administrativos.')) }, [token])
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
  async function decideRequest(id: string, decision: 'approve' | 'reject') {
    if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`${requestsEndpoint}/${encodeURIComponent(id)}/${decision}`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error(decision === 'approve' ? 'Não foi possível aprovar. Verifique o envio do convite e atualize a lista.' : 'Não foi possível recusar a solicitação.')
      await Promise.all([load(), loadRequests()])
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  return <details className="panel account-invitation-admin"><summary>Administração de convites</summary>
    <form onSubmit={create}><label htmlFor="invite-email">E-mail para convite</label><input id="invite-email" type="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/><button type="submit" disabled={busy}>{busy ? 'Processando…' : 'Enviar convite (7 dias)'}</button></form>
    {error && <p role="alert">{error}</p>}
    <ul>{items.map(item => <li key={item.id}><span>{item.email} · {item.revoked ? 'revogado' : item.accepted ? 'ativo' : `expira ${new Date(item.expires_at).toLocaleDateString('pt-BR')}`}</span>{!item.revoked && <button type="button" disabled={busy} onClick={() => void revoke(item.id)}>{item.accepted ? 'Revogar acesso' : 'Revogar convite'}</button>}</li>)}</ul>
    <section aria-labelledby="access-requests-title" className="access-requests-admin">
      <h3 id="access-requests-title">Solicitações de acesso</h3>
      <p>Os pedidos ficam visíveis aqui mesmo sem notificação por e-mail.</p>
      {!requests.length ? <p>Nenhuma solicitação registrada.</p> : <ul>{requests.map(item => <li key={item.id}>
        <span><strong>{item.email}</strong><br/><time dateTime={item.requested_at}>{new Date(item.requested_at).toLocaleString('pt-BR')}</time><br/>Status: {item.status === 'pending' ? item.processing ? 'aprovação em andamento' : 'pendente' : item.status === 'approved' ? 'aprovado' : 'recusado'}</span>
        {item.status === 'pending' && <span><button type="button" disabled={busy || item.processing} onClick={() => void decideRequest(item.id, 'approve')}>Aprovar e enviar convite</button> <button type="button" disabled={busy} onClick={() => void decideRequest(item.id, 'reject')}>{item.processing ? 'Cancelar aprovação' : 'Recusar'}</button></span>}
      </li>)}</ul>}
    </section>
  </details>
}
