import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { Navigate, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownLeft, ArrowUpRight, ChartNoAxesCombined, Wallet, FlaskConical, Plus, Download, X, ShieldCheck, ChevronRight, Eye, Trash2, RotateCcw, LogOut, LogIn, Menu, FlaskConical as DemoIcon } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from './components/ui/button'
import { ApiError } from './api'
import './style.css'
import './dashboard-ux.css'
import './navigation.css'
import { PUBLIC_DEMO, SUPABASE_AUTH } from './runtime'
import { useAuth } from './auth/useAuth'
import { getDisplayIdentity } from './auth/displayIdentity'
import { LoginPage } from './auth/LoginPage'
import { DemoRepository } from './repositories/DemoRepository'
import { PrivateRepository } from './repositories/PrivateRepository'
import type { OperationInput } from './demo/finance'
import { DemoAccessPage } from './demo/DemoAccessPage'
import { ConfirmDialog } from './components/ui/ConfirmDialog'
import { MarketDashboard } from './components/MarketDashboard'
import { FinancialHint } from './components/FinancialHint'
import { WorkspaceSidebar, workspaceNavItems } from './components/WorkspaceSidebar'
const FixedIncomePage = lazy(() => import('./fixed-income/FixedIncomePage').then(module => ({ default: module.FixedIncomePage })))
const PortfolioInsights = lazy(() => import('./portfolio/PortfolioInsights').then(module => ({ default: module.PortfolioInsights })))
const EquityHistory = lazy(() => import('./portfolio/EquityHistory').then(module => ({ default: module.EquityHistory })))
const IndividualEquityHistory = lazy(() => import('./portfolio/IndividualEquityHistory').then(module => ({ default: module.IndividualEquityHistory })))
const AssetComparison = lazy(() => import('./portfolio/AssetComparison').then(module => ({ default: module.AssetComparison })))
const MovementHistory = lazy(() => import('./portfolio/MovementHistory').then(module => ({ default: module.MovementHistory })))
const DemoFlowChart = lazy(() => import('./portfolio/DemoFlowChart').then(module => ({ default: module.DemoFlowChart })))

const money = (v: string | number) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const number = (v: string | number) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })
const palette = ['#68e5b4', '#8298f8', '#e8c77c', '#d494dc', '#7bc7e6', '#edac86']
const noSubscription = () => () => {}
const emptySnapshot = () => null

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const demo = PUBLIC_DEMO || location.pathname === '/demo' || location.pathname.startsWith('/demo/')
  const [token, setToken] = useState('')
  const [localConnected, setConnected] = useState(false)
  const [modal, setModal] = useState(false)
  const [error, setError] = useState('')
  const [fixedAccessError, setFixedAccessError] = useState<ApiError | null>(null)
  const [fixedNewRequest, setFixedNewRequest] = useState(0)
  const onFixedAuthError = useCallback((cause: ApiError) => setFixedAccessError(cause), [])
  const [confirmation, setConfirmation] = useState<{ kind: 'reset' } | { kind: 'delete'; id: number } | null>(null)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  const returnFocus = useRef<HTMLElement | null>(null)
  function askConfirmation(value: NonNullable<typeof confirmation>) { returnFocus.current = document.activeElement as HTMLElement; setConfirmError(''); setConfirmation(value) }
  const [period, setPeriod] = useState('Tudo')
  const [search, setSearch] = useState('')
  const [sortAsc, setSortAsc] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return window.localStorage.getItem('investment-sidebar-collapsed') === 'true' } catch { return false }
  })
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false)
  const client = useQueryClient()
  const clearPrivate = useCallback(() => { void client.cancelQueries(); client.clear(); setModal(false); setConfirmation(null); setConfirmError(''); setError(''); setFixedAccessError(null); setFixedNewRequest(0) }, [client])
  const auth = useAuth(!demo && SUPABASE_AUTH && !PUBLIC_DEMO, clearPrivate)
  const connected = !demo && (SUPABASE_AUTH ? auth.status === 'authenticated' && !!auth.session : localConnected)
  const activeToken = SUPABASE_AUTH ? auth.session?.access_token ?? '' : token
  const identity = SUPABASE_AUTH ? auth.session?.user.id ?? 'anonymous' : 'local'
  const demoRepository = useMemo(() => demo ? new DemoRepository() : null, [demo])
  const demoState = useSyncExternalStore(demoRepository?.subscribe ?? noSubscription, demoRepository?.getSnapshot ?? emptySnapshot)
  const privateRepository = useMemo(() => new PrivateRepository(activeToken), [activeToken])
  const page = demo && !PUBLIC_DEMO ? location.pathname.slice(5) || '/' : location.pathname
  useEffect(() => {
    try { window.localStorage.setItem('investment-sidebar-collapsed', String(sidebarCollapsed)) } catch { /* preferência opcional */ }
  }, [sidebarCollapsed])
  useEffect(() => { setMobileNavigationOpen(false) }, [location.pathname])
  useEffect(() => { if (page === '/cdbs') setModal(false) }, [page])
  const routeTo = (path: string) => demo && !PUBLIC_DEMO ? '/demo' + (path === '/' ? '' : path) : path
  const summary = useQuery({ queryKey: ['summary', identity], queryFn: ({ signal }) => privateRepository.summary(signal), enabled: connected && !demo, retry: false, staleTime: 30 * 60 * 1000, refetchInterval: false })
  const operations = useQuery({ queryKey: ['operations', identity], queryFn: ({ signal }) => privateRepository.list(signal), enabled: connected && !demo, retry: false })
  const data = demo ? demoState?.summary : connected ? summary.data : undefined
  const ops = demo ? demoState?.operations ?? [] : connected ? operations.data ?? [] : []
  const busy = summary.isFetching || operations.isFetching
  const queryErrors = [summary.error, operations.error, fixedAccessError]
  const apiError = demo ? null : queryErrors.find(cause => cause instanceof ApiError && cause.status === 401)
    || queryErrors.find(cause => cause instanceof ApiError && cause.status === 403)
    || summary.error || operations.error
  useEffect(() => {
    if (SUPABASE_AUTH && apiError instanceof ApiError && apiError.status === 401) auth.expire()
  }, [apiError, auth.expire])
  useEffect(() => {
    if (connected && SUPABASE_AUTH) { void client.invalidateQueries({ queryKey: ['summary', identity] }); void client.invalidateQueries({ queryKey: ['operations', identity] }) }
  }, [activeToken, connected, identity, client])
  function reportError(cause: unknown) {
    if (SUPABASE_AUTH && cause instanceof ApiError && cause.status === 401) { auth.expire(); return }
    setError((cause as Error).message)
  }
  async function toggleDemo() {
    clearPrivate(); setConnected(false); setToken('')
    if (!demo && SUPABASE_AUTH) await auth.logout()
    navigate(demo ? '/login' : '/demo')
  }
  const refresh = async () => { await client.invalidateQueries({ queryKey: ['summary'] }); await client.invalidateQueries({ queryKey: ['operations'] }) }
  const months = period === '1M' ? 1 : period === '3M' ? 3 : period === '6M' ? 6 : period === '1A' ? 12 : 0
  const cutoff = new Date(); cutoff.setMonth(cutoff.getMonth() - months)
  const filtered = ops.filter(o => (!months || o.date >= cutoff.toISOString().slice(0, 10)) && o.ticker.toLowerCase().includes(search.toLowerCase())).sort((a, b) => (sortAsc ? 1 : -1) * (a.date.localeCompare(b.date) || a.id - b.id))
  // Histórico de custo, sem atribuir valorização de mercado às compras.
  let running = 0
  const series = [...ops].sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id).map(o => { running += (o.kind === 'BUY' ? 1 : -1) * Number(o.quantity) * Number(o.price); return { date: o.date, value: running } }).filter(o => !months || o.date >= cutoff.toISOString().slice(0, 10))
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!demo && !connected) return; setError('')
    const form = new FormData(event.currentTarget)
    try { const input = Object.fromEntries(form) as OperationInput; if (demo) demoRepository!.create(input); else await privateRepository.create(input); setModal(false); if (!demo) await refresh() } catch (e) { reportError(e) }
  }
  async function exportData() {
    try {
      const payload = demo ? { demonstration: true, operations: demoState?.operations ?? [] } : await privateRepository.export()
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
      const a = document.createElement('a'); a.href = url; a.download = demo ? 'investment-demo.json' : 'investment-registros.json'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { reportError(e) }
  }
  function resetDemo() { if (demoRepository) askConfirmation({ kind: 'reset' }) }
  async function confirmAction() {
    if (!confirmation || confirmBusy) return
    setConfirmBusy(true); setConfirmError('')
    try {
      if (confirmation.kind === 'reset') { demoRepository!.reset(); setPeriod('Tudo'); setSearch(''); setError('') }
      else {
        if (demo) demoRepository!.delete(confirmation.id)
        else { await privateRepository.delete(confirmation.id); await refresh() }
      }
      setConfirmation(null)
    } catch (cause) {
      if (!demo && cause instanceof ApiError && cause.status === 401) { setConfirmation(null); reportError(cause) }
      else setConfirmError((cause as Error).message)
    } finally { setConfirmBusy(false) }
  }
  if (PUBLIC_DEMO && location.pathname === '/login') return <DemoAccessPage/>
  const accessDenied = apiError instanceof ApiError && (apiError.status === 401 || apiError.status === 403)
  const authorized = connected && summary.data !== undefined && operations.data !== undefined && !accessDenied
  const logout = () => { clearPrivate(); setConnected(false); setToken(''); if (SUPABASE_AUTH) void auth.logout(); navigate('/login', { replace: true }) }
  if (!demo && ((SUPABASE_AUTH && auth.status === 'loading') || (connected && !authorized && !accessDenied))) {
    return <main className="session-gate" aria-label="Verificando acesso à carteira"><ShieldCheck size={28}/><h1>Investment Dashboard</h1><p role={apiError ? 'alert' : 'status'}>{apiError ? (apiError as Error).message : 'Verificando acesso à carteira…'}</p>{apiError && <div><Button onClick={() => { void refresh() }}>Tentar novamente</Button><button onClick={logout}>Sair</button></div>}</main>
  }
  if (!demo && !authorized) {
    if (location.pathname !== '/login') return <Navigate to="/login" replace/>
    return <LoginPage loading={SUPABASE_AUTH ? auth.status === 'loading' || connected && !apiError : localConnected && !apiError} error={auth.error || error || (apiError as Error | null)?.message || ''} onLogin={auth.login} local={!SUPABASE_AUTH} onLocalLogin={value => { clearPrivate(); setToken(value); setConnected(true) }} onDemo={() => { void toggleDemo() }} connected={connected} onLogout={logout}/>
  }
  if (!demo && location.pathname === '/login') return <Navigate to="/" replace/>
  const sessionDisplay = getDisplayIdentity(SUPABASE_AUTH ? auth.session?.user : null)
  const displayName = demo ? 'Demonstração' : sessionDisplay.name
  const avatarInitial = demo ? 'D' : sessionDisplay.initial
  return <div className={`shell${sidebarCollapsed ? ' sidebar-is-collapsed' : ''}`} data-navigation-collapsed={sidebarCollapsed}>
    <WorkspaceSidebar demo={demo} routeTo={routeTo} collapsed={sidebarCollapsed} onToggleCollapsed={() => setSidebarCollapsed(value => !value)} displayName={displayName} avatarInitial={avatarInitial}/>
    <main><header><div className="mobile-header-brand"><span className="brand-icon"><ChartNoAxesCombined size={20}/></span>investment<span className="brand-dot">.</span></div><Dialog.Root open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}><Dialog.Trigger asChild><button type="button" className="mobile-menu-trigger" aria-label="Abrir menu de navegação" aria-controls="mobile-navigation-panel"><Menu size={20}/></button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="mobile-nav-overlay" onClick={() => setMobileNavigationOpen(false)}/><Dialog.Content id="mobile-navigation-panel" className="mobile-nav-content"><Dialog.Title className="sr-only">Menu de navegação</Dialog.Title><Dialog.Close type="button" className="mobile-nav-close" aria-label="Fechar menu de navegação" onClick={() => setMobileNavigationOpen(false)}><X size={19}/></Dialog.Close><WorkspaceSidebar demo={demo} routeTo={routeTo} mobile onNavigate={() => setMobileNavigationOpen(false)} displayName={displayName} avatarInitial={avatarInitial}/></Dialog.Content></Dialog.Portal></Dialog.Root><div className="breadcrumb">Workspace <ChevronRight size={13}/> <span>{workspaceNavItems.find(n => n.to === page)?.label}</span></div><span className="local-badge"><span className="status-dot"/> {demo ? 'Modo Demonstração' : 'Ambiente pessoal'}</span></header>

      <section className="page-title"><div><p className="eyebrow">CLAREZA PARA O SEU PRÓXIMO PASSO</p><h1>{workspaceNavItems.find(n => n.to === page)?.label ?? 'Página não encontrada'}</h1><p>Acompanhe suas escolhas. Construa seu amanhã.</p></div><div className="actions">{page !== '/cdbs' && <Button variant="outline" onClick={exportData} disabled={!demo && !connected}><Download size={16}/> Exportar</Button>}<Button onClick={() => page === '/cdbs' ? setFixedNewRequest(value => value + 1) : setModal(true)} disabled={!demo && !connected || demo && page === '/cdbs'}><Plus size={17}/> Nova operação</Button></div></section>
      <section className={demo ? 'mode-banner demo-banner' : 'mode-banner private-banner'} aria-label={demo ? 'Modo demonstração' : 'Conta conectada'}>
        <div className="mode-summary"><span className="mode-icon">{demo ? <DemoIcon size={20}/> : <ShieldCheck size={20}/>}</span><div><strong>{demo ? 'Modo demonstração' : 'Carteira conectada'}</strong><p>{demo ? 'Dados fictícios armazenados neste navegador' : auth.session?.user.email ?? 'Desenvolvimento local'}</p></div></div>
        <div className="mode-actions">{demo ? <><Button variant="outline" onClick={resetDemo}><RotateCcw size={16}/> Restaurar</Button><Button variant="outline" onClick={() => { void toggleDemo() }}><LogIn size={16}/> Entrar</Button></> : <><Button variant="outline" onClick={() => { void toggleDemo() }}><DemoIcon size={16}/> Explorar demonstração</Button><Button variant="outline" onClick={logout}><LogOut size={16}/> Sair</Button></>}</div>
      </section>
      {demoState?.notice && demo && <div className="connection" role="status">{demoState.notice}</div>}
      {(error || apiError) && <div className="error" role="alert">{error || (apiError as Error).message}<button onClick={() => {setError(''); void refresh()}}>Tentar novamente</button></div>}
      {busy && <p role="status">Carregando carteira…</p>}
      {(page === '/' || page === '/acoes') && <>
        <div className={demo ? 'metrics' : 'metrics private-cost-metrics'}><article className="metric featured"><div><span>Capital em ações · custo</span><Wallet size={19}/></div><h2>{data ? money(data.acquisition_cost) : 'R$ —'}</h2><small><span className="status-dot"/> Custo de aquisição da posição aberta</small><div className="metric-decoration"/></article><article className="metric"><div><span>Compras acumuladas</span><ArrowDownLeft size={19}/></div><h2>{data ? money(data.total_purchases) : 'R$ —'}</h2><small>Inclui taxas de aquisição</small></article><article className="metric"><div><span>Resultado realizado {!demo && <FinancialHint label="resultado realizado">Resultado das vendas após custo de aquisição e taxas registradas de compra e venda. Tributos não são calculados; separado das posições abertas.</FinancialHint>}</span><ChartNoAxesCombined size={19}/></div><h2 className={Number(data?.realized_profit) < 0 ? 'negative' : 'positive'}>{data ? money(data.realized_profit) : 'R$ —'}</h2><small>{demo ? 'Resultado líquido das vendas' : 'Vendas após taxas registradas; antes de tributos'}</small></article>{demo && <article className="metric"><div><span>Patrimônio a mercado</span><Eye size={19}/></div><h2 className="muted">Indisponível</h2><small>Sem cotações de mercado</small></article>}</div>
        {!demo && summary.data && <MarketDashboard snapshot={summary.data} updating={summary.isFetching} failed={summary.isError} onRefresh={() => { void refresh() }}/>}
        {!demo ? <Suspense fallback={<p role="status" className="panel">Carregando gráficos financeiros…</p>}><><PortfolioInsights repository={privateRepository} identity={identity}/><EquityHistory repository={privateRepository} identity={identity}/></></Suspense> : <div className="chart-grid"><Suspense fallback={<p role="status" className="panel">Carregando gráfico…</p>}><DemoFlowChart period={period} onPeriodChange={setPeriod} series={series}/></Suspense>
        <article className="panel allocation"><div className="panel-heading"><div><h3>Composição em ações</h3><p>Distribuição pelo custo de aquisição</p></div><span className="tag">B3</span></div><div className="donut" style={{ background: data?.holdings.length ? `conic-gradient(${data.holdings.map((h, i) => { const start = data.holdings.slice(0, i).reduce((sum, item) => sum + Number(item.cost), 0) / Number(data.acquisition_cost) * 100; const end = start + Number(h.cost) / Number(data.acquisition_cost) * 100; return `${palette[i % palette.length]} ${start}% ${end}%` }).join(', ')})` : '#253039' }}><div><span>Ativos em carteira</span><strong>{data?.holdings.length ?? 0}</strong></div></div><div className="allocation-list">{data?.holdings.map((h, i) => <div key={h.ticker}><span><i style={{ background: palette[i % palette.length] }}/>{h.ticker}</span><strong>{(Number(h.cost) / Number(data.acquisition_cost) * 100).toFixed(1)}%</strong></div>)}{!data?.holdings.length && <p>Nenhuma posição cadastrada.</p>}</div></article></div>}
        {demo && page === '/acoes' && <article className="panel"><div className="panel-heading"><h3>Posições por custo médio</h3></div><div className="table-scroll"><table><thead><tr><th>Ativo</th><th>Quantidade</th><th>Preço médio</th><th>Custo da posição</th></tr></thead><tbody>{data?.holdings.map(h => <tr key={h.ticker}><td>{h.ticker}</td><td>{number(h.quantity)}</td><td>{money(h.average_price)}</td><td>{money(h.cost)}</td></tr>)}</tbody></table></div></article>}
      </>}
      {!demo && page === '/acoes' && data && <Suspense fallback={<p role="status" className="panel">Carregando histórico de preços…</p>}><IndividualEquityHistory
        repository={privateRepository} identity={identity}
        tickers={data.holdings.map(holding => holding.ticker)}
      /></Suspense>}
      {!demo && page === '/acoes' && data && <Suspense fallback={<p role="status" className="panel">Carregando comparação…</p>}><AssetComparison
        repository={privateRepository} identity={identity}
        tickers={data.holdings.map(holding => holding.ticker)}
      /></Suspense>}
      {!demo && page === '/historico' && <Suspense fallback={<p role="status" className="panel">Carregando histórico de movimentações…</p>}><MovementHistory repository={privateRepository} identity={identity}/></Suspense>}
      {(page === '/' || page === '/acoes' || (page === '/historico' && demo)) && <article className="panel transactions"><div className="panel-heading"><div><h3>{page === '/' ? 'Últimas movimentações' : page === '/acoes' ? 'Operações em ações' : 'Histórico de operações'}</h3><p>Cada movimento, uma parte da sua trajetória.</p></div><input aria-label="Pesquisar ticker" placeholder="Buscar ativo…" value={search} onChange={e => setSearch(e.target.value)}/></div><div className="table-scroll"><table><thead><tr><th>Ativo</th><th>Operação</th><th aria-sort={sortAsc ? 'ascending' : 'descending'}><button aria-label="Ordenar por data" onClick={() => setSortAsc(!sortAsc)}>Data {sortAsc ? '↑' : '↓'}</button></th><th>Quantidade</th><th>Preço unitário</th><th>Taxas</th><th>Valor bruto</th><th/></tr></thead><tbody>{filtered.slice(0, page === '/' ? 5 : undefined).map(o => <tr key={o.id}><td><span className="ticker-icon">{o.ticker.slice(0, 2)}</span><strong>{o.ticker}</strong></td><td><span className={`operation-tag ${o.kind === 'SELL' ? 'sell' : ''}`}>{o.kind === 'BUY' ? <ArrowDownLeft size={12}/> : <ArrowUpRight size={12}/>} {o.kind === 'BUY' ? 'Compra' : 'Venda'}</span></td><td>{new Date(o.date + 'T12:00:00').toLocaleDateString('pt-BR')}</td><td>{number(o.quantity)}</td><td>{money(o.price)}</td><td>{money(o.fees)}</td><td>{money(Number(o.quantity) * Number(o.price))}</td><td>{<button aria-label={`Excluir operação ${o.id}`} className="icon-action delete-action" title={`Excluir operação de ${o.ticker}`} onClick={() => askConfirmation({ kind: 'delete', id: o.id })}><Trash2 size={15}/></button>}</td></tr>)}</tbody></table></div>{!filtered.length && <div className="empty compact"><p>Nenhuma movimentação encontrada.</p></div>}<div className="table-footer">{filtered.length} operações encontradas <NavLink to={routeTo("/historico")}>Ver histórico completo <ArrowUpRight size={14}/></NavLink></div></article>}
      {['/metas', '/simulador'].includes(page) && <article className="panel planned"><FlaskConical size={32}/><h2>{page === '/metas' ? 'Seu próximo marco financeiro' : 'Planeje o que vem pela frente'}</h2><p>{page === '/metas' ? 'Metas e projeções de conclusão estão planejadas para a Fase 5.' : 'Simulações com taxas hipotéticas e reinvestimento estão planejadas para a Fase 5.'}</p><span className="tag">Em breve · funcionalidade ainda indisponível</span></article>}
      {!demo && page === '/cdbs' && <Suspense fallback={<p role="status" className="panel">Carregando renda fixa…</p>}><FixedIncomePage key={identity} repository={privateRepository} identity={identity} newOperationRequest={fixedNewRequest} onAuthError={onFixedAuthError}/></Suspense>}
      {demo && page === '/cdbs' && <article className="panel planned"><h2>Renda fixa na carteira privada</h2><p>A demonstração permanece offline e não simula persistência de CDBs ou consultas de rendimento.</p><Button onClick={() => navigate(routeTo('/'))}>Voltar à demonstração</Button></article>}
      <footer><span><ShieldCheck size={13}/> Seus registros. Suas decisões.</span><span>Investment Dashboard · {demo ? 'Demonstração' : 'Carteira privada'}</span></footer>
    </main>
    <ConfirmDialog open={confirmation !== null} onClose={() => setConfirmation(null)} onConfirm={confirmAction} title={confirmation?.kind === 'delete' ? 'Excluir operação?' : 'Restaurar carteira demonstrativa?'} description={confirmation?.kind === 'delete' ? 'Esta operação será removida e os saldos serão recalculados. A exclusão será bloqueada se invalidar vendas posteriores.' : 'Suas operações fictícias serão substituídas pela nova carteira demonstrativa. Nenhum registro privado será alterado.'} confirmLabel={confirmation?.kind === 'delete' ? 'Excluir operação' : 'Restaurar carteira'} kind={confirmation?.kind ?? 'reset'} busy={confirmBusy} error={confirmError} returnFocus={returnFocus.current}/>
    <Dialog.Root open={modal && page !== '/cdbs'} onOpenChange={setModal}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="modal"><Dialog.Title>Nova operação</Dialog.Title><Dialog.Description>Registre uma compra ou venda de ações. Valores em reais.</Dialog.Description><Dialog.Close className="close" aria-label="Fechar"><X size={20}/></Dialog.Close><form onSubmit={save}><label>Ativo<input name="ticker" placeholder="ITUB4" required pattern="[A-Z0-9]{4,20}" maxLength={20}/></label><label>Operação<select name="kind"><option value="BUY">Compra</option><option value="SELL">Venda</option></select></label><label>Data<input name="date" type="date" required max={new Date().toLocaleDateString('en-CA')}/></label><label>Quantidade<input name="quantity" type="number" min="0.00000001" step="0.00000001" required/></label><label>Preço unitário<input name="price" type="number" min="0.00000001" step="0.00000001" required/></label><label>Taxas<input name="fees" type="number" min="0" step="0.00000001" defaultValue="0" required/></label>{error && <p className="negative" role="alert">{error}</p>}<Button type="submit">Salvar operação</Button></form></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>
}
