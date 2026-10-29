import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Decimal from 'decimal.js'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { ChartNoAxesCombined } from 'lucide-react'
import { formatFlowAxisTick } from './format'
import './portfolio.css'

type FlowPoint = { date: string; contributions: string; redemptions: string; sales: string; cumulative_contributions?: string; cumulative_withdrawals?: string; net_accumulated: string }
export type CapitalFlows = {
  period_start: string; period_end: string; coverage_start: string | null; coverage_end: string | null
  coverage: 'available' | 'partial' | 'unavailable'; points: FlowPoint[]
  gross_contributions: string; equity_purchases?: string; cdb_applications?: string
  redemptions: string; cdb_redemptions?: string; sales: string; equity_sale_proceeds?: string
  cumulative_contributions?: string; cumulative_withdrawals?: string; withdrawals: string; net_accumulated: string
  market_value: null; return: null
}
type Position = { asset: string; value: string; basis: string; as_of?: string }
export type Composition = {
  as_of: string; equities: Position[]; fixed_income: Position[]; declared_positions: Position[]
  missing_fixed_income: string[]; market_values: null; coverage: 'available' | 'partial'
  missing_components: string[]; equity_basis: string; fixed_income_basis: string; declared_values_separate: boolean
  class_totals: { equities_open_cost: string; fixed_income_open_principal: string; declared_positions: string }
}
const money = (value?: string | number | null) => {
  if (value === undefined || value === null) return '—'
  try {
    const decimal = new Decimal(String(value))
    if (!decimal.isFinite()) return '—'
    const [integer, fraction] = decimal.toDecimalPlaces(2).toFixed(2).split('.')
    return `R$\u00a0${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}`
  } catch { return '—' }
}
const decimalValue = (value?: string | null) => {
  if (value === undefined || value === null) return null
  try { const decimal = new Decimal(value); return decimal.isFinite() ? decimal : null } catch { return null }
}
const periods = ['1M', '3M', '6M', '1A', 'Tudo']
const flowSeries = { inflows: 'Compras + aplicações acumuladas', outflows: 'Vendas líquidas + resgates de principal', net: 'Fluxo líquido acumulado' }

export function PortfolioInsights({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [period, setPeriod] = useState('Tudo')
  const flows = useQuery({ queryKey: ['capital-flows', identity, period], queryFn: ({ signal }) => repository.capitalFlows(period, signal), retry: false })
  const lifetimeFlows = useQuery({ queryKey: ['capital-flows', identity, 'Tudo'], queryFn: ({ signal }) => repository.capitalFlows('Tudo', signal), retry: false })
  const composition = useQuery({ queryKey: ['portfolio-composition', identity], queryFn: ({ signal }) => repository.composition(signal), retry: false })
  const chartData = (flows.data?.points ?? []).filter(point => point.cumulative_contributions !== undefined && point.cumulative_withdrawals !== undefined).map(point => ({ date: point.date,
    inflows: Number(point.cumulative_contributions), inflows_exact: point.cumulative_contributions,
    outflows: Number(point.cumulative_withdrawals), outflows_exact: point.cumulative_withdrawals,
    net: Number(point.net_accumulated), net_exact: point.net_accumulated })) ?? []
  const equityCapital = decimalValue(composition.data?.class_totals.equities_open_cost)
  const fixedCapital = decimalValue(composition.data?.class_totals.fixed_income_open_principal)
  const appliedCapital = equityCapital && fixedCapital ? equityCapital.plus(fixedCapital) : null
  const capitalShare = (value: Decimal | null) => !value || !appliedCapital || appliedCapital.isZero() ? '—' : new Decimal(100).times(value).dividedBy(appliedCapital).toFixed(1).replace('.', ',')
  const equityShare = capitalShare(equityCapital)
  const fixedShare = capitalShare(fixedCapital)
  return <section className="portfolio-insights" aria-label="Fluxos e composição da carteira">
    <article className="panel evolution">
      <div className="panel-heading"><div><h3>Evolução dos fluxos de capital</h3><p>Compras e aplicações, vendas líquidas e resgates de principal · não representa patrimônio nem rentabilidade</p></div>
        <div className="periods">{periods.map(value => <button key={value} aria-pressed={period === value} className={period === value ? 'selected' : ''} onClick={() => setPeriod(value)}>{value}</button>)}</div>
      </div>
      {flows.isLoading ? <p role="status" className="empty compact">Carregando fluxos…</p> : flows.isError ? <p role="alert" className="empty compact">Não foi possível carregar a evolução dos fluxos.</p> : flows.data?.points.length && !chartData.length ? <p role="alert" className="empty compact">A resposta não contém os acumulados necessários para montar o gráfico.</p> : !chartData.length ? <div className="empty compact"><ChartNoAxesCombined/><h4>Sem fluxos no período</h4><p>Não há movimentações registradas na janela selecionada.</p></div> : <div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/><YAxis tickFormatter={formatFlowAxisTick} axisLine={false} tickLine={false}/>
        <Tooltip labelFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')} formatter={(value, name, item) => [money(String(item.payload[`${String(name)}_exact`] ?? value)), flowSeries[String(name) as keyof typeof flowSeries] ?? String(name)]}/><Legend formatter={value => flowSeries[String(value) as keyof typeof flowSeries] ?? String(value)}/>
        <Line type="stepAfter" dataKey="inflows" name="inflows" stroke="#8298f8" strokeWidth={2} dot={false} isAnimationActive={false}/><Line type="stepAfter" dataKey="outflows" name="outflows" stroke="#e8c77c" strokeWidth={2} dot={false} isAnimationActive={false}/><Line type="stepAfter" dataKey="net" name="net" stroke="#65e3b2" strokeWidth={2.5} dot={false} isAnimationActive={false}/>
      </LineChart></ResponsiveContainer></div>}
      {lifetimeFlows.isPending ? <p role="status" className="portfolio-coverage">Carregando totais históricos…</p> : lifetimeFlows.isError ? <p role="alert" className="portfolio-coverage">Não foi possível carregar os totais históricos.</p> : lifetimeFlows.data && <div className="portfolio-lifetime-totals"><div><span>Compras de ações + aplicações acumuladas</span><strong>{money(lifetimeFlows.data.cumulative_contributions)}</strong></div><div><span>Vendas após taxas + resgates de principal</span><strong>{money(lifetimeFlows.data.cumulative_withdrawals)}</strong></div><div><span>Fluxo líquido acumulado · não é lucro ou rentabilidade</span><strong>{money(lifetimeFlows.data.net_accumulated)}</strong></div></div>}
      {flows.data && <><div className="portfolio-flow-totals"><span>Compras de ações no período · inclui taxas <strong>{money(flows.data.equity_purchases)}</strong></span><span>Aplicações CDB · principal <strong>{money(flows.data.cdb_applications)}</strong></span><span>Vendas de ações · após taxas registradas <strong>{money(flows.data.equity_sale_proceeds)}</strong></span><span>Resgates CDB · principal <strong>{money(flows.data.cdb_redemptions)}</strong></span></div><div className="chart-footer">Cobertura {flows.data.coverage_start ? `desde ${new Date(`${flows.data.coverage_start}T12:00:00`).toLocaleDateString('pt-BR')}` : 'indisponível'}{flows.data.coverage === 'partial' && ' · parcial para o período selecionado'} <span>Valores registrados; patrimônio a mercado e rentabilidade de carteira indisponíveis</span></div></>}
    </article>
    <article className="panel composition-panel">
      <div className="panel-heading"><div><h3>Composição atual disponível</h3><p>Valores por base registrada · data-base {composition.data?.as_of ? new Date(`${composition.data.as_of}T12:00:00`).toLocaleDateString('pt-BR') : '—'}</p></div><span className="tag">{composition.data?.coverage === 'partial' ? 'Cobertura parcial' : 'Privado'}</span></div>
      {composition.isLoading ? <p role="status" className="empty compact">Carregando composição…</p> : composition.isError ? <p role="alert" className="empty compact">Não foi possível carregar a composição da carteira.</p> : composition.data && <>
        {composition.data.missing_components.length > 0 && <p className="portfolio-coverage">Dados ausentes: {composition.data.missing_components.join('; ')}. Valores de mercado das ações indisponíveis.</p>}
        <div className="portfolio-applied-capital"><div><span>Capital aplicado contabilizado em posições abertas</span><strong>{money(appliedCapital?.toString())}</strong></div><ul><li><span>Ações · custo aberto com taxas</span><strong>{money(equityCapital?.toString())} · {equityShare === '—' ? equityShare : `${equityShare}%`}</strong></li><li><span>CDB · principal efetivo</span><strong>{money(fixedCapital?.toString())} · {fixedShare === '—' ? fixedShare : `${fixedShare}%`}</strong></li></ul><p>Posições CDB informadas manualmente ficam separadas e não entram neste total. Ações são avaliadas pelo custo de aquisição, não por cotação atual.</p></div>
        <div className="portfolio-composition-charts">
          <AssetDonut title="Ações · custo aberto" items={composition.data.equities} totalValue={composition.data.class_totals.equities_open_cost}/>
          <AssetDonut title="Renda fixa · principal efetivo" items={composition.data.fixed_income} totalValue={composition.data.class_totals.fixed_income_open_principal}/>
          <div className="portfolio-basis-chart"><h4>Bases disponíveis · sem total agregado</h4><p>Posições declaradas permanecem em série separada.</p><div className="portfolio-basis-chart-canvas"><ResponsiveContainer width="100%" height="100%"><BarChart data={[
            { name: 'Ações · custo aberto', value: Number(composition.data.class_totals.equities_open_cost) },
            { name: 'RF · principal ledger', value: Number(composition.data.class_totals.fixed_income_open_principal) },
            { name: 'Observações declaradas', value: Number(composition.data.class_totals.declared_positions) },
          ]} layout="vertical" margin={{ left: 14, right: 18 }}><XAxis type="number" hide/><YAxis type="category" dataKey="name" width={138} tick={{ fill: '#a9bac2', fontSize: 10 }}/><Tooltip formatter={value => money(String(value))}/><Bar dataKey="value" fill="#68e5b4" radius={[0, 5, 5, 0]}>{[0, 1, 2].map(index => <Cell key={index} fill={['#8298f8', '#68e5b4', '#e8c77c'][index]}/>)}</Bar></BarChart></ResponsiveContainer></div></div>
        </div>
        <h4>Renda variável · custo de aquisição aberto</h4><PositionList items={composition.data.equities}/>
        <h4>Renda fixa · principal efetivo aberto</h4><PositionList items={composition.data.fixed_income}/>
        <h4>Posições declaradas · observações separadas</h4><PositionList items={composition.data.declared_positions}/>
        {composition.data.missing_fixed_income.length > 0 && <p className="portfolio-coverage">Sem valor disponível: {composition.data.missing_fixed_income.join(', ')}.</p>}
      </>}
    </article>
  </section>
}

function AssetDonut({ title, items, totalValue }: { title: string; items: Position[]; totalValue: string }) {
  const total = Number(totalValue)
  return <div className="portfolio-asset-chart"><h4>{title}</h4>{items.length && total > 0 ? <><div className="portfolio-donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={items.map(item => ({ name: item.asset, value: Number(item.value) }))} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="86%" paddingAngle={2}><Cell fill="#68e5b4"/>{items.slice(1).map((_, index) => <Cell key={index} fill={['#8298f8', '#e8c77c', '#d494dc', '#7bc7e6', '#edac86'][index % 5]}/>)}</Pie><Tooltip formatter={value => money(String(value))}/></PieChart></ResponsiveContainer></div><ul className="portfolio-chart-legend">{items.map((item, index) => <li key={`${item.asset}-${index}`}><span>{item.asset}</span><strong>{(Number(item.value) / total * 100).toFixed(1)}%</strong></li>)}</ul></> : <p className="portfolio-coverage">Sem posições disponíveis.</p>}</div>
}

function PositionList({ items }: { items: Position[] }) {
  return items.length ? <ul className="portfolio-position-list">{items.map((item, index) => <li key={`${item.asset}-${index}`}><span>{item.asset}{item.as_of && <small> · posição em {new Date(`${item.as_of}T12:00:00`).toLocaleDateString('pt-BR')}</small>}</span><strong>{money(item.value)}</strong></li>)}</ul> : <p className="portfolio-coverage">Sem posições disponíveis.</p>
}
