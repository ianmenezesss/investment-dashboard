import { ChartNoAxesCombined, ChevronRight, Flag, FlaskConical, History, Landmark, LayoutDashboard, PanelLeftClose, PanelLeftOpen, ShieldCheck } from 'lucide-react'
import { NavLink } from 'react-router-dom'

export const workspaceNavItems = [
  { to: '/', label: 'Visão geral', icon: LayoutDashboard },
  { to: '/acoes', label: 'Ações', icon: ChartNoAxesCombined },
  { to: '/cdbs', label: 'Renda fixa', icon: Landmark },
  { to: '/historico', label: 'Histórico', icon: History },
  { to: '/simulador', label: 'Simulador', icon: FlaskConical },
  { to: '/metas', label: 'Metas', icon: Flag },
] as const

type WorkspaceSidebarProps = {
  demo: boolean
  routeTo: (path: string) => string
  collapsed?: boolean
  onToggleCollapsed?: () => void
  onNavigate?: () => void
  mobile?: boolean
  displayName: string
  avatarInitial: string
}

export function WorkspaceSidebar({ demo, routeTo, collapsed = false, onToggleCollapsed, onNavigate, mobile = false, displayName, avatarInitial }: WorkspaceSidebarProps) {
  const items = workspaceNavItems.filter(item => !demo || ['/', '/acoes', '/historico'].includes(item.to))
  const sidebarClass = ['sidebar', collapsed && !mobile && 'sidebar-collapsed', mobile && 'mobile-sidebar'].filter(Boolean).join(' ')

  return <aside className={sidebarClass} aria-label="Navegação da carteira">
    <div className="sidebar-header">
      <NavLink className="brand" aria-label="Investment Dashboard · Visão geral" to={routeTo('/')} onClick={onNavigate}>
        <span className="brand-icon" aria-hidden="true"><ChartNoAxesCombined size={23}/></span>
        <span className="brand-word">investment</span><span className="brand-dot">.</span>
      </NavLink>
      {!mobile && onToggleCollapsed && <button type="button" className="sidebar-collapse-toggle" aria-label={collapsed ? 'Expandir navegação' : 'Recolher navegação'} aria-controls="desktop-primary-navigation" aria-expanded={!collapsed} title={collapsed ? 'Expandir navegação' : 'Recolher navegação'} onClick={onToggleCollapsed}>
        {collapsed ? <PanelLeftOpen size={17}/> : <PanelLeftClose size={17}/>}
      </button>}
    </div>
    <div className="workspace" aria-label="Meu patrimônio, carteira pessoal"><div className="avatar" aria-hidden="true">{avatarInitial}</div><div>Meu patrimônio<small>Carteira pessoal</small></div><ChevronRight size={16} aria-hidden="true"/></div>
    <p className="nav-caption">WORKSPACE</p>
    <nav id={mobile ? undefined : 'desktop-primary-navigation'} aria-label="Navegação principal">
      {items.map(item => {
        const Icon = item.icon
        const planned = ['/simulador', '/metas'].includes(item.to)
        return <NavLink end to={routeTo(item.to)} key={item.to} aria-label={`${item.label}${planned ? ' (Em breve)' : ''}`} title={item.label} onClick={onNavigate}>
          <Icon size={19} aria-hidden="true"/><span className="nav-label">{item.label}</span>{planned && <span className="nav-planned">Em breve</span>}
        </NavLink>
      })}
    </nav>
    <div className="sidebar-bottom"><ShieldCheck size={22} aria-hidden="true"/><p>Seu futuro começa aqui.<small>Uma decisão de cada vez.</small></p></div>
    <div className="profile" aria-label={`Perfil: ${displayName}; ${demo ? 'Carteira demonstrativa' : 'Acesso privado'}`}>
      <div className="avatar" aria-hidden="true">{avatarInitial}</div><div className="profile-copy" title={displayName}>{displayName}<small>{demo ? 'Carteira demonstrativa' : 'Acesso privado'}</small></div><span className="status-dot" aria-hidden="true"/>
    </div>
  </aside>
}
