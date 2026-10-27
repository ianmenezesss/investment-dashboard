import React, { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts'
import { ArrowDownLeft, ArrowUpRight, ChartNoAxesCombined, LayoutDashboard, Wallet, Landmark, History, FlaskConical, Flag, Plus, Download, X, ShieldCheck, ChevronRight, Eye, Trash2 } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from './components/ui/button'
import { request, type Operation, type Summary } from './api'
import './style.css'
import { PUBLIC_DEMO } from './runtime'

const money = (v: string | number) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const number = (v: string | number) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })
const demoOps: Operation[] = [
  { id: 1, ticker: 'ITUB4', kind: 'BUY', date: '2026-01-15', quantity: '100', price: '32.50', fees: '0' },
  { id: 2, ticker: 'BBAS3', kind: 'BUY', date: '2026-03-10', quantity: '200', price: '25.20', fees: '0' },
  { id: 3, ticker: 'B3SA3', kind: 'BUY', date: '2026-05-06', quantity: '300', price: '12.40', fees: '0' },
  { id: 4, ticker: 'ITUB4', kind: 'BUY', date: '2026-07-20', quantity: '150', price: '34.00', fees: '0' },
]
const demoSummary: Summary = { acquisition_cost: '17110', total_purchases: '17110', sale_proceeds: '0', realized_profit: '0', market_value: null, holdings: [{ ticker: 'ITUB4', quantity: '250', cost: '8350', average_price: '33.4' }, { ticker: 'BBAS3', quantity: '200', cost: '5040', average_price: '25.2' }, { ticker: 'B3SA3', quantity: '300', cost: '3720', average_price: '12.4' }] }
const nav = [{ to: '/', label: 'Visão geral', icon: LayoutDashboard }, { to: '/acoes', label: 'Ações', icon: ChartNoAxesCombined }, { to: '/cdbs', label: 'Renda fixa', icon: Landmark }, { to: '/historico', label: 'Histórico', icon: History }, { to: '/simulador', label: 'Simulador', icon: FlaskConical }, { to: '/metas', label: 'Metas', icon: Flag }]

export default function App() {
  const [demo, setDemo] = useState(PUBLIC_DEMO)
  const [token, setToken] = useState('')
  const [connected, setConnected] = useState(false)
  const [modal, setModal] = useState(false)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState('Tudo')
  const [search, setSearch] = useState('')
  const [sortAsc, setSortAsc] = useState(false)
  const client = useQueryClient()
  const page = useLocation().pathname
  const summary = useQuery({ queryKey: ['summary'], queryFn: ({ signal }) => request<Summary>('dashboard', token, { signal }), enabled: connected && !demo, retry: false })
  const operations = useQuery({ queryKey: ['operations'], queryFn: ({ signal }) => request<Operation[]>('operations', token, { signal }), enabled: connected && !demo, retry: false })
  const data = demo ? demoSummary : connected ? summary.data : undefined
  const ops = demo ? demoOps : connected ? operations.data ?? [] : []
  const busy = summary.isFetching || operations.isFetching
  const apiError = demo ? null : summary.error || operations.error
  const refresh = async () => { await client.invalidateQueries({ queryKey: ['summary'] }); await client.invalidateQueries({ queryKey: ['operations'] }) }
  const months = period === '1M' ? 1 : period === '3M' ? 3 : period === '6M' ? 6 : period === '1A' ? 12 : 0
  const cutoff = new Date(); cutoff.setMonth(cutoff.getMonth() - months)
  const filtered = ops.filter(o => (!months || o.date >= cutoff.toISOString().slice(0, 10)) && o.ticker.toLowerCase().includes(search.toLowerCase())).sort((a, b) => (sortAsc ? 1 : -1) * (a.date.localeCompare(b.date) || a.id - b.id))
  // Histórico de custo, sem atribuir valorização de mercado às compras.
  let running = 0
  const series = [...ops].sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id).map(o => { running += (o.kind === 'BUY' ? 1 : -1) * Number(o.quantity) * Number(o.price); return { date: o.date, value: running } }).filter(o => !months || o.date >= cutoff.toISOString().slice(0, 10))
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (demo || !connected || PUBLIC_DEMO) return; setError('')
    const form = new FormData(event.currentTarget)
    try { await request('operations', token, { method: 'POST', body: JSON.stringify(Object.fromEntries(form)) }); setModal(false); await refresh() } catch (e) { setError((e as Error).message) }
  }
  async function remove(id: number) {
    if (demo || !connected || PUBLIC_DEMO) return
    if (!window.confirm('Excluir esta operação e recalcular a carteira?')) return
    try { await request(`operations/${id}`, token, { method: 'DELETE' }); await refresh() } catch (e) { setError((e as Error).message) }
  }
  async function exportData() {
    try {
      const payload = demo ? { demonstration: true, operations: demoOps } : await request('export', token)
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
      const a = document.createElement('a'); a.href = url; a.download = demo ? 'investment-demo.json' : 'investment-registros.json'; a.click(); URL.revokeObjectURL(url)
    } catch (e) { setError((e as Error).message) }
  }
  return <div className="shell">
    <aside className="sidebar"><a className="brand" href="/"><span className="brand-icon"><ChartNoAxesCombined size={23}/></span> investment<span className="brand-dot">.</span></a><div className="workspace"><div className="avatar">IP</div><div>Meu patrimônio<small>Carteira pessoal</small></div><ChevronRight size={16}/></div><p className="nav-caption">WORKSPACE</p><nav>{nav.map(n => <NavLink end to={n.to} key={n.to}><n.icon size={19}/>{n.label}</NavLink>)}</nav><div className="sidebar-bottom"><ShieldCheck size={22}/><p>Seu futuro começa aqui.<small>Uma decisão de cada vez.</small></p></div><div className="profile"><div className="avatar">EU</div><div>Investidor pessoal<small>Ambiente local · Fase 1</small></div><span className="status-dot"/></div></aside>
    <main><header><div className="breadcrumb">Workspace <ChevronRight size={13}/> <span>{nav.find(n => n.to === page)?.label}</span></div><span className="local-badge"><span className="status-dot"/> {PUBLIC_DEMO ? 'Modo Demonstração' : 'Ambiente pessoal'}</span></header>
      <section className="page-title"><div><p className="eyebrow">CLAREZA PARA O SEU PRÓXIMO PASSO</p><h1>{nav.find(n => n.to === page)?.label ?? 'Página não encontrada'}</h1><p>Acompanhe suas escolhas. Construa seu amanhã.</p></div><div className="actions"><Button variant="outline" onClick={exportData} disabled={!demo && !connected}><Download size={16}/> Exportar</Button><Button onClick={() => setModal(true)} disabled={demo || !connected}><Plus size={17}/> Nova operação</Button></div></section>
      <div className="connection"><div><span className={`status-dot ${demo ? 'amber' : ''}`}/><strong>{demo ? 'Modo Demonstração · dados fictícios' : connected ? 'Carteira pessoal' : 'Conecte sua carteira'}</strong><span>{demo ? 'Sem cotações externas. Nenhum registro real é alterado.' : 'Token mantido somente nesta sessão da página.'}</span></div><div className="connection-actions">{!connected && !demo && <><input aria-label="Token da API" type="password" placeholder="Token da API" value={token} onChange={e => setToken(e.target.value)}/><Button variant="outline" disabled={!token} onClick={() => setConnected(true)}>Conectar</Button></>}<button hidden={PUBLIC_DEMO} className="text-button" onClick={() => { void client.cancelQueries(); client.clear(); setConnected(false); setToken(''); setModal(false); setDemo(!demo); setError('') }}>{demo ? 'Sair da demonstração' : 'Explorar demonstração'} <ArrowUpRight size={14}/></button>{connected && <button className="text-button" onClick={() => {void client.cancelQueries(); setConnected(false); setToken(''); client.clear()}}>Desconectar</button>}</div></div>
      {(error || apiError) && <div className="error" role="alert">{error || (apiError as Error).message}<button onClick={() => {setError(''); void refresh()}}>Tentar novamente</button></div>}
      {busy && <p role="status">Carregando carteira…</p>}
      {(page === '/' || page === '/acoes') && <>
        <div className="metrics"><article className="metric featured"><div><span>Capital em ações · custo</span><Wallet size={19}/></div><h2>{data ? money(data.acquisition_cost) : 'R$ —'}</h2><small><span className="status-dot"/> Custo de aquisição da posição aberta</small><div className="metric-decoration"/></article><article className="metric"><div><span>Compras acumuladas</span><ArrowDownLeft size={19}/></div><h2>{data ? money(data.total_purchases) : 'R$ —'}</h2><small>Inclui taxas de aquisição</small></article><article className="metric"><div><span>Resultado realizado</span><ChartNoAxesCombined size={19}/></div><h2 className={Number(data?.realized_profit) < 0 ? 'negative' : 'positive'}>{data ? money(data.realized_profit) : 'R$ —'}</h2><small>Resultado líquido das vendas</small></article><article className="metric"><div><span>Patrimônio a mercado</span><Eye size={19}/></div><h2 className="muted">Indisponível</h2><small>Cadastre cotações em uma próxima fase</small></article></div>
        <div className="chart-grid"><article className="panel evolution"><div className="panel-heading"><div><h3>Fluxo acumulado de operações</h3><p>Compras menos vendas, sem taxas · não representa rentabilidade</p></div><div className="periods">{['1M', '3M', '6M', '1A', 'Tudo'].map(p => <button className={period === p ? 'selected' : ''} key={p} onClick={() => setPeriod(p)}>{p}</button>)}</div></div>{series.length ? <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={series} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}><defs><linearGradient id="green" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#65e3b2" stopOpacity={0.22}/><stop offset="100%" stopColor="#65e3b2" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={v => new Date(v + 'T12:00:00').toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false} tick={{ fill: '#7e8b96', fontSize: 11 }} dy={12}/><YAxis tickFormatter={v => `${v / 1000} mil`} axisLine={false} tickLine={false} tick={{ fill: '#7e8b96', fontSize: 11 }}/><Tooltip contentStyle={{ background: '#151e25', border: '1px solid #33414c', borderRadius: 10 }} formatter={v => [money(Number(v)), 'Fluxo acumulado']} labelFormatter={v => new Date(v + 'T12:00:00').toLocaleDateString('pt-BR')}/><Area type="stepAfter" dataKey="value" stroke="#65e3b2" strokeWidth={2.5} fill="url(#green)"/></AreaChart></ResponsiveContainer></div> : <div className="empty"><ChartNoAxesCombined/><h4>Sua história começa no primeiro aporte</h4><p>Registre uma operação ou explore os dados de demonstração.</p></div>}<div className="chart-footer"><span className="legend-dot"/> Fluxo das operações <span>Sem índices de referência nesta fase</span></div></article>
        <article className="panel allocation"><div className="panel-heading"><div><h3>Composição em ações</h3><p>Distribuição pelo custo de aquisição</p></div><span className="tag">B3</span></div><div className="donut" style={{ background: data?.holdings.length ? `conic-gradient(${data.holdings.map((h, i) => { const start = data.holdings.slice(0, i).reduce((sum, item) => sum + Number(item.cost), 0) / Number(data.acquisition_cost) * 100; const end = start + Number(h.cost) / Number(data.acquisition_cost) * 100; return `${['#68e5b4', '#8298f8', '#e8c77c'][i % 3]} ${start}% ${end}%` }).join(', ')})` : '#253039' }}><div><span>Ativos em carteira</span><strong>{data?.holdings.length ?? 0}</strong></div></div><div className="allocation-list">{data?.holdings.map((h, i) => <div key={h.ticker}><span><i style={{ background: ['#68e5b4', '#8298f8', '#e8c77c'][i % 3] }}/>{h.ticker}</span><strong>{(Number(h.cost) / Number(data.acquisition_cost) * 100).toFixed(1)}%</strong></div>)}{!data?.holdings.length && <p>Nenhuma posição cadastrada.</p>}</div></article></div>
        {page === '/acoes' && <article className="panel"><div className="panel-heading"><h3>Posições por custo médio</h3></div><div className="table-scroll"><table><thead><tr><th>Ativo</th><th>Quantidade</th><th>Preço médio</th><th>Custo da posição</th></tr></thead><tbody>{data?.holdings.map(h => <tr key={h.ticker}><td>{h.ticker}</td><td>{number(h.quantity)}</td><td>{money(h.average_price)}</td><td>{money(h.cost)}</td></tr>)}</tbody></table></div></article>}
      </>}
      {(page === '/' || page === '/historico') && <article className="panel transactions"><div className="panel-heading"><div><h3>{page === '/' ? 'Últimas movimentações' : 'Histórico de operações'}</h3><p>Cada movimento, uma parte da sua trajetória.</p></div><input aria-label="Pesquisar ticker" placeholder="Buscar ativo…" value={search} onChange={e => setSearch(e.target.value)}/></div><div className="table-scroll"><table><thead><tr><th>Ativo</th><th>Operação</th><th><button onClick={() => setSortAsc(!sortAsc)}>Data {sortAsc ? '↑' : '↓'}</button></th><th>Quantidade</th><th>Preço unitário</th><th>Taxas</th><th>Valor bruto</th><th/></tr></thead><tbody>{filtered.slice(0, page === '/' ? 5 : undefined).map(o => <tr key={o.id}><td><span className="ticker-icon">{o.ticker.slice(0, 2)}</span><strong>{o.ticker}</strong></td><td><span className={`operation-tag ${o.kind === 'SELL' ? 'sell' : ''}`}>{o.kind === 'BUY' ? <ArrowDownLeft size={12}/> : <ArrowUpRight size={12}/>} {o.kind === 'BUY' ? 'Compra' : 'Venda'}</span></td><td>{new Date(o.date + 'T12:00:00').toLocaleDateString('pt-BR')}</td><td>{number(o.quantity)}</td><td>{money(o.price)}</td><td>{money(o.fees)}</td><td>{money(Number(o.quantity) * Number(o.price))}</td><td>{!demo && <button aria-label={`Excluir operação ${o.id}`} onClick={() => remove(o.id)}><Trash2 size={15}/></button>}</td></tr>)}</tbody></table></div>{!filtered.length && <div className="empty compact"><p>Nenhuma movimentação encontrada.</p></div>}<div className="table-footer">{filtered.length} operações encontradas <NavLink to="/historico">Ver histórico completo <ArrowUpRight size={14}/></NavLink></div></article>}
      {['/cdbs', '/metas', '/simulador'].includes(page) && <article className="panel planned"><FlaskConical size={32}/><h2>{page === '/cdbs' ? 'Renda fixa, com precisão por lote' : page === '/metas' ? 'Seu próximo marco financeiro' : 'Planeje o que vem pela frente'}</h2><p>{page === '/cdbs' ? 'Cadastro de CDBs, aportes e resgates por lote serão implementados na Fase 3, junto aos cálculos e testes tributários.' : page === '/metas' ? 'Metas e projeções de conclusão estão planejadas para a Fase 5.' : 'Simulações com taxas hipotéticas e reinvestimento estão planejadas para a Fase 5.'}</p><span className="tag">Planejado · consulte docs/architecture.md</span></article>}
      <footer><span><ShieldCheck size={13}/> Seus registros. Suas decisões.</span><span>Investment Dashboard · Fase 1 {demo && '· Demonstração'}</span></footer>
    </main>
    <Dialog.Root open={modal} onOpenChange={setModal}><Dialog.Portal><Dialog.Overlay className="overlay"/><Dialog.Content className="modal"><Dialog.Title>Nova operação</Dialog.Title><Dialog.Description>Registre uma compra ou venda de ações. Valores em reais.</Dialog.Description><Dialog.Close className="close" aria-label="Fechar"><X size={20}/></Dialog.Close><form onSubmit={save}><label>Ativo<input name="ticker" placeholder="ITUB4" required pattern="[A-Z0-9]{4,20}" maxLength={20}/></label><label>Operação<select name="kind"><option value="BUY">Compra</option><option value="SELL">Venda</option></select></label><label>Data<input name="date" type="date" required max={new Date().toLocaleDateString('en-CA')}/></label><label>Quantidade<input name="quantity" type="number" min="0.00000001" step="0.00000001" required/></label><label>Preço unitário<input name="price" type="number" min="0.00000001" step="0.00000001" required/></label><label>Taxas<input name="fees" type="number" min="0" step="0.00000001" defaultValue="0" required/></label>{error && <p className="negative" role="alert">{error}</p>}<Button type="submit">Salvar operação</Button></form></Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>
}
