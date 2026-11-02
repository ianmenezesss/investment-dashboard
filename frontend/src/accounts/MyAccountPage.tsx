import { ArrowLeft, AtSign, ShieldCheck, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AccountDeletionPanel } from './AccountDeletionPanel'
import { InvitationAdmin } from './InvitationAdmin'
import './my-account.css'

type Props = {
  name: string
  email: string
  isAdmin: boolean
  status: string
  accessStatus: 'active' | 'trial_expired'
  activatedAt: string | null
  expiresAt: string | null
  identity: string
  token: string
  reauthenticate: (password: string) => Promise<{ access_token: string }>
  onDeleted: (goalsCleared: boolean) => Promise<void>
}

function localDate(value: string | null) {
  if (!value) return 'Não registrado'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Não registrado' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function MyAccountPage({ name, email, isAdmin, status, accessStatus, activatedAt, expiresAt, identity, token, reauthenticate, onDeleted }: Props) {
  return <div className="account-page">
    <Link className="account-back" to="/"><ArrowLeft size={16}/> Voltar à carteira</Link>
    <section className="panel account-card" aria-labelledby="account-information-title">
      <div className="account-section-heading"><span className="account-section-icon"><UserRound size={19}/></span><div><h2 id="account-information-title">Informações da conta</h2><p>Identidade e nível de acesso desta sessão.</p></div></div>
      <dl className="account-details">
        <div><dt>Nome</dt><dd>{name}</dd></div>
        <div><dt>E-mail autenticado</dt><dd><AtSign size={14}/>{email || 'Não informado pela sessão'}</dd></div>
        <div><dt>Tipo de acesso</dt><dd><ShieldCheck size={14}/>{isAdmin ? 'Administrador' : 'Usuário'}</dd></div>
        <div><dt>Status</dt><dd><span className="account-status-dot"/>{status}</dd></div>
        <div><dt>Plano de acesso</dt><dd>{expiresAt ? 'Teste de 7 dias' : 'Permanente'}</dd></div>
        <div><dt>Ativada em</dt><dd>{localDate(activatedAt)}</dd></div>
        {expiresAt && <div><dt>{accessStatus === 'trial_expired' ? 'Expirou em' : 'Expira em'}</dt><dd>{localDate(expiresAt)}</dd></div>}
      </dl>
    </section>

    {isAdmin && <section className="panel account-card" aria-labelledby="account-admin-title">
      <div className="account-section-heading"><span className="account-section-icon"><ShieldCheck size={19}/></span><div><h2 id="account-admin-title">Administração</h2><p>Gerencie o acesso por convite. As permissões são verificadas pelo servidor em cada ação.</p></div></div>
      <InvitationAdmin token={token}/>
    </section>}

    <section className="account-card account-danger" aria-labelledby="account-danger-title">
      <div className="account-section-heading"><span className="account-section-icon"><ShieldCheck size={19}/></span><div><h2 id="account-danger-title">Segurança e privacidade</h2><p>Controles de segurança e privacidade da sua conta.</p></div></div>
      <div className="account-danger-zone"><h3>Zona de perigo</h3><p>A exclusão remove permanentemente sua carteira, observações, convites e identidade Supabase. Ela não pode ser desfeita.</p>
        <AccountDeletionPanel identity={identity} reauthenticate={reauthenticate} onDeleted={onDeleted}/>
      </div>
    </section>
  </div>
}
