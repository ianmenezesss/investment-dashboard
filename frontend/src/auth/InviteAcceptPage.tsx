import { useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { getSupabase } from './supabase'
import { InvitePasswordPage } from './InvitePasswordPage'
import { parseInvitationCallback, restoreInvitationSession } from './invitationCallback'

export function InvitationOriginError() {
  useEffect(() => { window.history.replaceState(window.history.state, '', '/invite/accept') }, [])
  return <main className="session-gate"><p role="alert">Este endereço é a demonstração pública. O convite precisa ser aberto no endereço privado da plataforma. Solicite ao administrador um link com o domínio correto.</p></main>
}

export function InviteAcceptPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [callback] = useState(() => parseInvitationCallback(new URL(location.pathname + location.search + location.hash, window.location.origin).href))
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const pending = useRef<Promise<Session> | null>(null)

  useEffect(() => {
    let active = true
    // Remove tokens and provider error text before making requests or rendering forms.
    window.history.replaceState(window.history.state, '', callback.cleanPath)
    if (!pending.current) {
      pending.current = (async () => {
        const client = getSupabase()
        if (!client) throw new Error('auth_unavailable')
        return restoreInvitationSession(client, callback)
      })()
    }
    void pending.current.then(next => { if (active) setSession(next) }).catch(() => {
      if (active) setError('Este link expirou, já foi utilizado ou não pôde ser validado. Solicite um novo convite ao administrador. Se o link usa PKCE, abra-o no mesmo navegador em que o acesso foi iniciado.')
    })
    return () => { active = false }
  }, [callback])

  if (error) return <main className="session-gate"><p role="alert">{error}</p><Button onClick={() => navigate('/login', { replace: true })}>Ir para o login</Button></main>
  if (!session) return <main className="session-gate" role="status">Validando convite…</main>
  return <InvitePasswordPage invitationId={callback.invitationId} token={session.access_token} onComplete={() => navigate('/', { replace: true })}/>
}
