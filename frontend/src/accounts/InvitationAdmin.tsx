import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiBase } from '../runtime'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import './invitation-admin.css'

type PageData<T> = { items: T[]; page: number; page_size: number; total: number; total_pages: number }
type Invitation = {
  id: string; email: string; created_at: string; expires_at: string; status: 'pending' | 'accepted' | 'expired' | 'revoked'
  email_send_status: 'not_requested' | 'started' | 'requested' | 'failed' | 'uncertain'; email_send_attempts: number
  can_resend?: boolean; max_send_attempts?: number; retry_after_seconds?: number
  send_history: { attempted_at: string; outcome: string; method: string; http_status: number | null; provider_code?: string | null }[]
}
type AccessRequest = {
  id: string; email: string; requested_at: string; status: 'pending' | 'approved' | 'rejected'; processing?: boolean
  invitation_id?: string | null; email_send_status?: string
}
type Membership = {
  user_id: string; email: string | null; account_label: string; email_source: string
  status: 'active' | 'expired' | 'revoked'; access_type: 'trial' | 'permanent'
  activated_at: string | null; trial_expires_at: string | null
  can_reactivate: boolean; can_revoke: boolean; protected_admin: boolean
}
type Tab = 'accounts' | 'invitations' | 'requests'
type RevokeTarget = { id: string; label: string }

const PAGE_SIZE = 5
const endpoint = `${apiBase()}/api/admin`

function dateTime(value: string | null) {
  if (!value) return 'Não registrado'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Não registrado' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function statusLabel(status: string) {
  return ({ active: 'Ativa', expired: 'Expirada', revoked: 'Revogada', pending: 'Pendente', accepted: 'Aceito', approved: 'Aprovada', rejected: 'Recusada' } as Record<string, string>)[status] ?? status
}

function sendStatusLabel(status: string) {
  return ({
    not_requested: 'Envio ainda não solicitado',
    started: 'Solicitação de envio em andamento',
    requested: 'Solicitação aceita pelo Supabase · entrega não confirmada',
    failed: 'Envio recusado pelo Supabase',
    uncertain: 'Resultado incerto · confirme com o destinatário antes de reenviar',
  } as Record<string, string>)[status] ?? status
}

async function errorMessage(response: Response, fallback: string) {
  try {
    const payload = await response.json() as { detail?: string | { message?: string } }
    return typeof payload.detail === 'string' ? payload.detail
      : typeof payload.detail?.message === 'string' ? payload.detail.message : fallback
  } catch { return fallback }
}

export function InvitationAdmin({ token }: { token: string }) {
  const [activeTab, setActiveTab] = useState<Tab>('accounts')
  const [members, setMembers] = useState<PageData<Membership>>({ items: [], page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0 })
  const [invitations, setInvitations] = useState<PageData<Invitation>>({ items: [], page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0 })
  const [requests, setRequests] = useState<PageData<AccessRequest>>({ items: [], page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0 })
  const [pages, setPages] = useState<Record<Tab, number>>({ accounts: 1, invitations: 1, requests: 1 })
  const [statusFilters, setStatusFilters] = useState<Record<Tab, string>>({ accounts: 'all', invitations: 'all', requests: 'all' })
  const [search, setSearch] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const mutationInFlight = useRef(false)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [error, setError] = useState('')
  const [loadErrors, setLoadErrors] = useState<Record<Tab, string>>({ accounts: '', invitations: '', requests: '' })
  const [success, setSuccess] = useState('')
  const [revokeTarget, setRevokeTarget] = useState<RevokeTarget | null>(null)
  const [returnFocus, setReturnFocus] = useState<HTMLElement | null>(null)
  const [dialogBusy, setDialogBusy] = useState(false)
  const [dialogError, setDialogError] = useState('')
  const [confirmResendInvitationId, setConfirmResendInvitationId] = useState<string | null>(null)
  const currentPage = pages[activeTab]

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const query = (tab: Tab) => {
      const params = new URLSearchParams({ page: String(pages[tab]), page_size: String(PAGE_SIZE), search: search.trim(), status: statusFilters[tab] })
      return params.toString()
    }
    const get = async <T,>(path: string, tab: Tab): Promise<PageData<T>> => {
      const response = await fetch(`${endpoint}/${path}?${query(tab)}`, {
        headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
      })
      if (!response.ok) throw new Error(await errorMessage(response, 'Não foi possível carregar os dados administrativos.'))
      return response.json() as Promise<PageData<T>>
    }
    setLoading(true); setLoadErrors({ accounts: '', invitations: '', requests: '' })
    void Promise.allSettled([
      get<Membership>('members', 'accounts'), get<Invitation>('invitations', 'invitations'),
      get<AccessRequest>('access-requests', 'requests'),
    ]).then(([nextMembers, nextInvitations, nextRequests]) => {
      if (!active) return
      if (nextMembers.status === 'fulfilled') setMembers(nextMembers.value)
      if (nextInvitations.status === 'fulfilled') setInvitations(nextInvitations.value)
      if (nextRequests.status === 'fulfilled') setRequests(nextRequests.value)
      const message = (result: PromiseSettledResult<unknown>) => result.status === 'rejected' && result.reason?.name !== 'AbortError'
        ? result.reason?.message || 'Não foi possível atualizar esta lista. Tente novamente.' : ''
      setLoadErrors({ accounts: message(nextMembers), invitations: message(nextInvitations), requests: message(nextRequests) })
      setPages(current => {
        const next = {
          accounts: nextMembers.status === 'fulfilled' ? Math.min(current.accounts, Math.max(1, nextMembers.value.total_pages)) : current.accounts,
          invitations: nextInvitations.status === 'fulfilled' ? Math.min(current.invitations, Math.max(1, nextInvitations.value.total_pages)) : current.invitations,
          requests: nextRequests.status === 'fulfilled' ? Math.min(current.requests, Math.max(1, nextRequests.value.total_pages)) : current.requests,
        }
        return next.accounts === current.accounts && next.invitations === current.invitations && next.requests === current.requests
          ? current : next
      })
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [token, pages, search, statusFilters, reloadKey])

  function changeTab(tab: Tab) {
    setActiveTab(tab); setSuccess(''); setError('')
  }
  function updatePage(page: number) { setPages(current => ({ ...current, [activeTab]: page })) }
  function updateStatusFilter(status: string) {
    setStatusFilters(current => ({ ...current, [activeTab]: status }))
    setPages(current => ({ ...current, [activeTab]: 1 }))
  }

  async function mutate(path: string, method: string, body: unknown, successText: string, fallback: string, sendsEmail = false) {
    if (mutationInFlight.current) return
    mutationInFlight.current = true
    setBusy(true); setError(''); setSuccess('')
    try {
      const response = await fetch(`${endpoint}/${path}`, {
        method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      if (!response.ok) throw new Error(await errorMessage(response, fallback))
      const payload = await response.json().catch(() => ({})) as { status?: string; email_send_status?: string }
      if (sendsEmail && ['failed', 'uncertain', 'started'].includes(payload.email_send_status ?? payload.status ?? '')) {
        throw new Error('A operação foi registrada, mas o envio não foi confirmado. Consulte o estado e o histórico na aba Convites.')
      }
      setSuccess(sendsEmail && payload.email_send_status !== 'requested' && payload.status !== 'requested'
        ? 'A operação foi registrada. Consulte o estado do envio na aba Convites; a entrega do e-mail não foi confirmada.' : successText)
      setReloadKey(value => value + 1)
      return true
    } catch (cause) {
      setError((cause as Error).message || fallback)
      setReloadKey(value => value + 1)
      return false
    } finally { mutationInFlight.current = false; setBusy(false) }
  }

  async function create(event: FormEvent) {
    event.preventDefault()
    const result = await mutate('invitations', 'POST', { email, expires_in_days: 7 },
      'O Supabase aceitou a solicitação de envio. A entrega do e-mail não é confirmada por este sistema.',
      'Não foi possível criar/enviar o convite.', true)
    if (result) setEmail('')
  }

  async function decideRequest(id: string, decision: 'approve' | 'reject') {
    await mutate(`access-requests/${encodeURIComponent(id)}/${decision}`, 'POST', undefined,
      decision === 'approve' ? 'A solicitação foi aprovada e o pedido de envio foi aceito pelo Supabase; entrega não confirmada.' : 'A solicitação foi recusada.',
      decision === 'approve' ? 'A aprovação ou o envio não foi confirmado.' : 'Não foi possível recusar a solicitação.', decision === 'approve')
  }

  async function reactivate(userId: string) {
    await mutate(`members/${encodeURIComponent(userId)}/reactivate`, 'POST', undefined,
      'O Supabase aceitou a solicitação do link de reativação; entrega não confirmada.',
      'Não foi possível solicitar a reativação.', true)
  }

  async function resend(invitation: Invitation) {
    if (invitation.email_send_status === 'uncertain' && confirmResendInvitationId !== invitation.id) {
      setConfirmResendInvitationId(invitation.id)
      return
    }
    const label = invitation.email_send_status === 'requested' ? 'Reenvio solicitado ao Supabase; entrega não confirmada.' : 'Nova tentativa solicitada ao Supabase; entrega não confirmada.'
    const result = await mutate(`invitations/${encodeURIComponent(invitation.id)}/resend`, 'POST', undefined, label,
      'Não foi possível solicitar novo envio. Verifique o histórico e os limites do Supabase.', true)
    if (result) setConfirmResendInvitationId(null)
  }

  function askRevoke(target: RevokeTarget) {
    setReturnFocus(document.activeElement as HTMLElement)
    setDialogError(''); setError(''); setSuccess(''); setRevokeTarget(target)
  }

  async function confirmRevoke() {
    if (!revokeTarget || mutationInFlight.current) return
    mutationInFlight.current = true
    setDialogBusy(true); setDialogError('')
    try {
      const response = await fetch(`${endpoint}/members/${encodeURIComponent(revokeTarget.id)}/revoke`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error(await errorMessage(response, 'Não foi possível revogar o acesso.'))
      setRevokeTarget(null); setError(''); setSuccess('Acesso financeiro revogado. Os dados e a identidade Supabase foram preservados.')
      setReloadKey(value => value + 1)
    } catch (cause) { setSuccess(''); setDialogError((cause as Error).message || 'Não foi possível revogar o acesso.'); setReloadKey(value => value + 1) }
    finally { mutationInFlight.current = false; setDialogBusy(false) }
  }

  const pageData = activeTab === 'accounts' ? members : activeTab === 'invitations' ? invitations : requests
  const hasItems = pageData.items.length > 0
  const label = activeTab === 'accounts' ? 'contas' : activeTab === 'invitations' ? 'convites' : 'solicitações'

  return <>
    <details className="panel account-invitation-admin"><summary>Administração</summary>
      <nav className="admin-tabs" aria-label="Seções de administração">
        <button id="admin-tab-accounts" type="button" aria-current={activeTab === 'accounts' ? 'page' : undefined} onClick={() => changeTab('accounts')}>Contas <span>{members.total}</span></button>
        <button id="admin-tab-invitations" type="button" aria-current={activeTab === 'invitations' ? 'page' : undefined} onClick={() => changeTab('invitations')}>Convites <span>{invitations.total}</span></button>
        <button id="admin-tab-requests" type="button" aria-current={activeTab === 'requests' ? 'page' : undefined} onClick={() => changeTab('requests')}>Solicitações <span>{requests.total}</span></button>
      </nav>

      {loadErrors[activeTab] && <p role="alert" className="admin-message error">{loadErrors[activeTab]} <button type="button" disabled={loading} onClick={() => setReloadKey(value => value + 1)}>Atualizar lista</button></p>}
      {error && <p role="alert" className="admin-message error">{error}</p>}
      {success && <p role="status" className="admin-message success">{success}</p>}
      <div className="admin-filters">
        <label htmlFor="admin-search">Buscar por e-mail</label>
        <input id="admin-search" type="search" value={search} maxLength={320} onChange={event => { setSearch(event.target.value); setPages({ accounts: 1, invitations: 1, requests: 1 }) }} placeholder="nome@exemplo.com"/>
        <label htmlFor="admin-status">Status</label>
        <select id="admin-status" value={statusFilters[activeTab]} onChange={event => updateStatusFilter(event.target.value)}>
          <option value="all">Todos</option>
          {activeTab === 'accounts' && <><option value="active">Ativa</option><option value="expired">Expirada</option><option value="revoked">Revogada</option></>}
          {activeTab === 'invitations' && <><option value="pending">Pendente</option><option value="accepted">Aceito</option><option value="expired">Expirado</option><option value="revoked">Revogado</option></>}
          {activeTab === 'requests' && <><option value="pending">Pendente</option><option value="approved">Aprovada</option><option value="rejected">Recusada</option></>}
        </select>
        <button type="button" disabled={loading || busy || dialogBusy} onClick={() => setReloadKey(value => value + 1)}>Atualizar listas</button>
      </div>

      {activeTab === 'accounts' && <section id="admin-panel-accounts" aria-label="Contas" className="admin-tab-panel">
        <h3>Contas</h3>
        {loading ? <p role="status">Carregando contas…</p> : !hasItems ? <p className="admin-empty">Nenhuma conta corresponde aos filtros.</p> : <ul>{members.items.map(member => <li key={member.user_id}>
          <span><strong>{member.account_label}</strong>{!member.email && <><br/><small>E-mail não confirmado ou indisponível no Supabase · ID final {member.user_id.slice(-8)}</small></>}<br/>
            {member.access_type === 'trial' ? 'Teste de 7 dias' : 'Acesso permanente'} · {statusLabel(member.status)}<br/>
            Ativada em: {dateTime(member.activated_at)}{member.trial_expires_at && <><br/>{member.status === 'expired' ? 'Expirou em: ' : 'Expira em: '}{dateTime(member.trial_expires_at)}</>}
          </span>
          <span className="admin-row-actions">
            {member.protected_admin && <small>Conta administrativa protegida</small>}
            {member.can_revoke && <button type="button" disabled={busy} onClick={() => askRevoke({ id: member.user_id, label: member.account_label })}>Revogar acesso</button>}
            {member.can_reactivate && <button type="button" disabled={busy} onClick={() => void reactivate(member.user_id)}>Conceder novo teste (7 dias)</button>}
          </span>
        </li>)}</ul>}
      </section>}

      {activeTab === 'invitations' && <section id="admin-panel-invitations" aria-label="Convites" className="admin-tab-panel">
        <h3>Convites</h3>
        <form onSubmit={create} className="admin-invite-form"><label htmlFor="invite-email">Enviar convite permanente · validade do link de até 7 dias</label>
          <input id="invite-email" type="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/>
          <button type="submit" disabled={busy}>{busy ? 'Processando…' : 'Enviar convite'}</button>
        </form>
        {loading ? <p role="status">Carregando convites…</p> : !hasItems ? <p className="admin-empty">Nenhum convite corresponde aos filtros.</p> : <ul>{invitations.items.map(invitation => <li key={invitation.id}>
          <span><strong>{invitation.email}</strong><br/>{statusLabel(invitation.status)} · Link até {dateTime(invitation.expires_at)}<br/>
            Estado do e-mail: {sendStatusLabel(invitation.email_send_status)} · tentativas {invitation.email_send_attempts}{invitation.max_send_attempts ? `/${invitation.max_send_attempts}` : ''}
            {!!invitation.retry_after_seconds && <><br/>Nova tentativa em aproximadamente {Math.ceil(invitation.retry_after_seconds / 60)} minuto(s). Atualize a lista após esse prazo.</>}
            {invitation.send_history.length > 0 && <details className="send-history"><summary>Histórico de envio</summary><ol>{invitation.send_history.map((attempt, index) => <li key={`${attempt.attempted_at}-${index}`}>
              {dateTime(attempt.attempted_at)} · {sendStatusLabel(attempt.outcome)} · {attempt.method === 'recovery' ? 'recovery' : 'convite'}{attempt.http_status ? ` · HTTP ${attempt.http_status}` : ''}{attempt.provider_code ? ` · ${attempt.provider_code}` : ''}
            </li>)}</ol></details>}
          </span>
          <span className="admin-row-actions">
            {invitation.status === 'pending' && invitation.email_send_status !== 'started' && invitation.can_resend !== false && (!invitation.max_send_attempts || invitation.email_send_attempts < invitation.max_send_attempts) && <button type="button" disabled={busy} onClick={() => void resend(invitation)}>{invitation.email_send_status === 'requested' ? 'Reenviar e-mail' : 'Tentar envio novamente'}</button>}
            {invitation.status === 'pending' && <button type="button" disabled={busy || invitation.email_send_status === 'started'} onClick={() => void mutate(`invitations/${encodeURIComponent(invitation.id)}`, 'DELETE', undefined, 'Convite pendente revogado.', 'Não foi possível revogar o convite.')}>Revogar convite</button>}
          </span>
          {confirmResendInvitationId === invitation.id && <div className="admin-resend-confirm" role="group" aria-label="Confirmar reenvio de resultado incerto">
            <p>O pedido anterior teve resultado incerto. Confirme com a pessoa antes de solicitar outro e-mail, pois o primeiro pode ter sido enviado.</p>
            <button type="button" disabled={busy} onClick={() => void resend(invitation)}>Confirmar nova tentativa</button>
            <button type="button" disabled={busy} onClick={() => setConfirmResendInvitationId(null)}>Cancelar</button>
          </div>}
        </li>)}</ul>}
        <p className="admin-note">“Solicitação aceita” confirma resposta do Supabase, não entrega. Os limites configurados no backend e no provedor de e-mail continuam válidos.</p>
      </section>}

      {activeTab === 'requests' && <section id="admin-panel-requests" aria-label="Solicitações de acesso" className="admin-tab-panel">
        <h3>Solicitações de acesso</h3>
        <p className="admin-note">Os pedidos ficam visíveis aqui mesmo sem notificação por e-mail.</p>
        {loading ? <p role="status">Carregando solicitações…</p> : !hasItems ? <p className="admin-empty">Nenhuma solicitação corresponde aos filtros.</p> : <ul>{requests.items.map(item => <li key={item.id}>
          <span><strong>{item.email}</strong><br/><time dateTime={item.requested_at}>{dateTime(item.requested_at)}</time><br/>Status: {item.processing ? 'aprovação em andamento' : statusLabel(item.status)}
            {item.email_send_status && <><br/>{sendStatusLabel(item.email_send_status)}</>}
            {item.status === 'approved' && item.invitation_id && <><br/><button type="button" onClick={() => { setSearch(item.email); setPages({ accounts: 1, invitations: 1, requests: 1 }); changeTab('invitations') }}>Consultar convite e tentativas de envio</button></>}
          </span>
          <span className="admin-row-actions">{item.status === 'pending' && <><button type="button" disabled={busy || item.processing} onClick={() => void decideRequest(item.id, 'approve')}>Aprovar e enviar convite</button><button type="button" disabled={busy} onClick={() => void decideRequest(item.id, 'reject')}>{item.processing ? 'Cancelar aprovação' : 'Recusar'}</button></>}</span>
        </li>)}</ul>}
      </section>}

      <nav className="admin-pagination" aria-label={`Paginação de ${label}`}>
        <span>{pageData.total === 0 ? '0 registros' : `${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, pageData.total)} de ${pageData.total}`}</span>
        <div><button type="button" disabled={loading || currentPage <= 1} onClick={() => updatePage(currentPage - 1)}>Anterior</button><span>Página {pageData.total_pages ? pageData.page : 0} de {pageData.total_pages}</span><button type="button" disabled={loading || currentPage >= pageData.total_pages} onClick={() => updatePage(currentPage + 1)}>Próxima</button></div>
      </nav>
    </details>
    <ConfirmDialog open={revokeTarget !== null} onClose={() => setRevokeTarget(null)} onConfirm={confirmRevoke}
      title="Revogar acesso à plataforma?" description={`${revokeTarget?.label ?? 'Esta conta'} perderá o acesso financeiro imediatamente, inclusive em uma sessão ainda válida. Os dados financeiros e a identidade Supabase serão preservados.`}
      confirmLabel="Revogar acesso" kind="delete" busy={dialogBusy} error={dialogError} returnFocus={returnFocus}/>
  </>
}
