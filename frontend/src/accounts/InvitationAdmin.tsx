import { useEffect, useState, type FormEvent } from 'react'
import { apiBase } from '../runtime'
import './invitation-admin.css'

type Invitation = { id: string; email: string; expires_at: string; accepted: boolean; revoked: boolean }
type AccessRequest = { id: string; email: string; requested_at: string; status: 'pending' | 'approved' | 'rejected'; processing?: boolean }
type Membership = { user_id: string; email: string | null; status: 'active' | 'expired' | 'revoked'; access_type: 'trial' | 'permanent'; activated_at: string | null; trial_expires_at: string | null; can_reactivate: boolean }

function dateTime(value: string | null) {
  if (!value) return 'Não registrado'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Não registrado' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function InvitationAdmin({ token }: { token: string }) {
  const [items, setItems] = useState<Invitation[]>([])
  const [members, setMembers] = useState<Membership[]>([])
  const [requests, setRequests] = useState<AccessRequest[]>([])
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const endpoint = `${apiBase()}/api/admin/invitations`
  const requestsEndpoint = `${apiBase()}/api/admin/access-requests`
  const membersEndpoint = `${apiBase()}/api/admin/members`
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
  async function loadMembers() {
    const response = await fetch(membersEndpoint, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Não foi possível carregar os status de acesso.')
    setMembers(await response.json())
  }
  async function reload() { await Promise.all([load(), loadRequests(), loadMembers()]) }
  useEffect(() => { void reload().catch(() => setError('Não foi possível carregar os dados administrativos.')) }, [token])
  async function create(event: FormEvent) {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(endpoint, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ email, expires_in_days: 7 }) })
      if (!response.ok) throw new Error('Não foi possível enviar o convite. Verifique o limite e a configuração do Supabase.')
      setEmail(''); await reload()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  async function revoke(id: string) {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${endpoint}/${encodeURIComponent(id)}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('Não foi possível revogar o convite/acesso.')
      await reload()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  async function decideRequest(id: string, decision: 'approve' | 'reject') {
    if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`${requestsEndpoint}/${encodeURIComponent(id)}/${decision}`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error(decision === 'approve' ? 'Não foi possível aprovar. Verifique o envio do convite e atualize a lista.' : 'Não foi possível recusar a solicitação.')
      await reload()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  async function reactivate(userId: string) {
    if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`${membersEndpoint}/${encodeURIComponent(userId)}/reactivate`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw new Error('Não foi possível conceder novo período. Verifique o status da conta e atualize a lista.')
      await reload()
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }
  return <details className="panel account-invitation-admin"><summary>Administração de convites</summary>
    <form onSubmit={create}><label htmlFor="invite-email">E-mail para convite permanente · o link expira em até 7 dias</label><input id="invite-email" type="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/><button type="submit" disabled={busy}>{busy ? 'Processando…' : 'Enviar convite permanente'}</button></form>
    {error && <p role="alert">{error}</p>}
    <section aria-labelledby="member-access-title" className="member-access-admin">
      <h3 id="member-access-title">Contas e status de acesso</h3>
      {!members.length ? <p>Nenhuma membership registrada.</p> : <ul>{members.map(member => <li key={member.user_id}>
        <span><strong>{member.email ?? 'E-mail indisponível'}</strong><br/>{member.access_type === 'trial' ? 'Teste de 7 dias' : 'Acesso permanente'} · {member.status === 'active' ? 'Ativa' : member.status === 'expired' ? 'Expirada' : 'Revogada'}<br/>Ativada em: {dateTime(member.activated_at)}{member.trial_expires_at && <><br/>{member.status === 'expired' ? 'Expirou em: ' : 'Expira em: '}{dateTime(member.trial_expires_at)}</>}</span>
        {member.can_reactivate && <button type="button" disabled={busy} onClick={() => void reactivate(member.user_id)}>{busy ? 'Processando…' : 'Conceder novo teste (7 dias)'}</button>}
      </li>)}</ul>}
    </section>
    <section aria-labelledby="invite-history-title" className="invitation-history-admin"><h3 id="invite-history-title">Histórico de convites</h3>
      {!items.length ? <p>Nenhum convite registrado.</p> : <ul>{items.map(item => <li key={item.id}><span><strong>{item.email}</strong><br/>{item.revoked ? 'Revogado' : item.accepted ? 'Aceito' : new Date(item.expires_at).getTime() <= Date.now() ? 'Expirado' : `Pendente · link até ${dateTime(item.expires_at)}`}</span>{!item.revoked && !item.accepted && <button type="button" disabled={busy} onClick={() => void revoke(item.id)}>Revogar convite</button>}</li>)}</ul>}
    </section>
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
