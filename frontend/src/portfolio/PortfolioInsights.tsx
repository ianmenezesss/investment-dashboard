import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Decimal from 'decimal.js'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import type { CapitalFlows, FinancialPerformance, PortfolioComposition } from '../api'
import { ChartNoAxesCombined } from 'lucide-react'
import { formatFlowAxisTick } from './format'
import './portfolio.css'
import './performance.css'

export type { CapitalFlows, PortfolioComposition as Composition } from '../api'
type Position = PortfolioComposition['equities'][number]
const money = (value?: string | number | null) => {
  if (value === undefined || value === null) return '—'
  try {
    const decimal = new Decimal(String(value))
    if (!decimal.isFinite()) return '—'
    const [integer, fraction] = decimal.toDecimalPlaces(2).toFixed(2).split('.')
    return `R$\u00a0${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}`
  } catch { return '—' }
}
const periods = ['1M', '3M', '6M', '1A', 'Tudo']
const flowSeries = { inflows: 'Compras + aplicações acumuladas', outflows: 'Vendas líquidas + resgates de principal', net: 'Fluxo líquido acumulado' }

export function PortfolioInsights({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [period, setPeriod] = useState('Tudo')
  const flows = useQuery({ queryKey: ['capital-flows', identity, period], queryFn: ({ signal }) => repository.capitalFlows(period, signal), retry: false })
  const performance = useQuery({ queryKey: ['financial-performance', identity], queryFn: ({ signal }) => repository.performance(signal), retry: false })
  const eventSummary = useQuery({ queryKey: ['financial-event-summary', identity, period], queryFn: ({ signal }) => repository.financialEventSummary(period, signal), retry: false, enabled: typeof repository.financialEventSummary === 'function' })
  const chartData = (flows.data?.points ?? []).filter(point => point.cumulative_contributions !== undefined && point.cumulative_withdrawals !== undefined).map(point => ({ date: point.date,
    inflows: Number(point.cumulative_contributions), inflows_exact: point.cumulative_contributions,
    outflows: Number(point.cumulative_withdrawals), outflows_exact: point.cumulative_withdrawals,
    net: Number(point.net_accumulated), net_exact: point.net_accumulated })) ?? []
  const composition = performance.data?.composition
  const lifetimeFlows = performance.data?.flows
  const equityCapital = performance.data?.capital.equities_open_cost
  const fixedCapital = performance.data?.capital.fixed_income_open_principal
  const appliedCapital = performance.data?.capital.open_positions_accounted
  const equityShare = performance.data?.capital.equity_open_share_percent ?? null
  const fixedShare = performance.data?.capital.fixed_income_open_share_percent ?? null
  const combinedResult = performance.data?.equities.combined_result_before_tax ?? null
  const combinedTone = combinedResult === null ? '' : new Decimal(combinedResult).isNegative() ? 'negative' : 'positive'
  return <section className="portfolio-insights" aria-label="Fluxos e composição da carteira">
    <article className="panel portfolio-performance-result">
      <div className="panel-heading"><div><h3>Resultado acumulado em ações</h3><p>Vendas realizadas + posições abertas · antes de impostos</p></div><ChartNoAxesCombined size={18}/></div>
      {performance.isLoading ? <p role="status" className="empty compact">Carregando resumo financeiro…</p> : performance.isError ? <p role="alert" className="empty compact">Não foi possível carregar o resumo financeiro.</p> : performance.data && <>
        {combinedResult === null ? <p role="status" className="portfolio-coverage">Resultado combinado indisponível com cobertura {performance.data.equities.combined_result_status}. Cotações ausentes: {performance.data.equities.valuation.missing_tickers.join(', ') || 'dados de mercado indisponíveis'}. O resultado realizado continua separado no resumo de ações.</p> : <div className="portfolio-combined-result"><span>Resultado realizado + não realizado coberto</span><strong className={combinedTone}>{money(combinedResult)}</strong></div>}
        {performance.data.equities.valuation.status === 'stale' && <p role="status" className="portfolio-coverage">A estimativa inclui cotações desatualizadas. Confira os valores atuais diretamente na corretora.</p>}
        <p className="portfolio-coverage">Não é rentabilidade total da carteira: faltam fluxos externos, proventos e avaliações históricas. Estimativas de CDB permanecem por contrato na página de renda fixa.</p>
      </>}
    </article>
    <article className="panel evolution">
      <div className="panel-heading"><div><h3>Evolução dos fluxos de capital</h3><p>Compras e aplicações, vendas líquidas e resgates de principal · não representa patrimônio nem rentabilidade</p></div>
        <div className="periods">{periods.map(value => <button key={value} aria-pressed={period === value} className={period === value ? 'selected' : ''} onClick={() => setPeriod(value)}>{value}</button>)}</div>
      </div>
      {flows.isLoading ? <p role="status" className="empty compact">Carregando fluxos…</p> : flows.isError ? <p role="alert" className="empty compact">Não foi possível carregar a evolução dos fluxos.</p> : flows.data?.points.length && !chartData.length ? <p role="alert" className="empty compact">A resposta não contém os acumulados necessários para montar o gráfico.</p> : !chartData.length ? <div className="empty compact"><ChartNoAxesCombined/><h4>Sem fluxos no período</h4><p>Não há movimentações registradas na janela selecionada.</p></div> : <div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/><YAxis tickFormatter={formatFlowAxisTick} axisLine={false} tickLine={false}/>
        <Tooltip labelFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')} formatter={(value, name, item) => [money(String(item.payload[`${String(name)}_exact`] ?? value)), flowSeries[String(name) as keyof typeof flowSeries] ?? String(name)]}/><Legend formatter={value => flowSeries[String(value) as keyof typeof flowSeries] ?? String(value)}/>
        <Line type="stepAfter" dataKey="inflows" name="inflows" stroke="#8298f8" strokeWidth={2} dot={false} isAnimationActive={false}/><Line type="stepAfter" dataKey="outflows" name="outflows" stroke="#e8c77c" strokeWidth={2} dot={false} isAnimationActive={false}/><Line type="stepAfter" dataKey="net" name="net" stroke="#65e3b2" strokeWidth={2.5} dot={false} isAnimationActive={false}/>
      </LineChart></ResponsiveContainer></div>}
      {performance.isLoading ? <p role="status" className="portfolio-coverage">Carregando totais históricos…</p> : performance.isError ? <p role="alert" className="portfolio-coverage">Não foi possível carregar os totais históricos.</p> : lifetimeFlows && <div className="portfolio-lifetime-totals"><div><span>Compras de ações + aplicações acumuladas</span><strong>{money(lifetimeFlows.recorded_contributions)}</strong></div><div><span>Vendas após taxas + resgates de principal</span><strong>{money(lifetimeFlows.recorded_withdrawals)}</strong></div><div><span>Fluxo líquido acumulado · não é lucro ou rentabilidade</span><strong>{money(lifetimeFlows.net_recorded_flow)}</strong></div></div>}
      {flows.data && <><div className="portfolio-flow-totals"><span>Compras de ações no período · inclui taxas <strong>{money(flows.data.equity_purchases)}</strong></span><span>Aplicações CDB · principal <strong>{money(flows.data.cdb_applications)}</strong></span><span>Vendas de ações · após taxas registradas <strong>{money(flows.data.equity_sale_proceeds)}</strong></span><span>Resgates CDB · principal <strong>{money(flows.data.cdb_redemptions)}</strong></span></div><div className="chart-footer">Cobertura {flows.data.coverage_start ? `desde ${new Date(`${flows.data.coverage_start}T12:00:00`).toLocaleDateString('pt-BR')}` : 'indisponível'}{flows.data.coverage === 'partial' && ' · parcial para o período selecionado'} <span>Valores registrados; patrimônio a mercado e rentabilidade de carteira indisponíveis</span></div></>}
    </article>
    {typeof repository.financialEventSummary === 'function' && <article className="panel financial-event-insights">
      <div className="panel-heading"><div><h3>Caixa externo e proventos registrados</h3><p>Período {period} · valores informados manualmente · não são rentabilidade</p></div></div>
      {eventSummary.isPending ? <p role="status" className="portfolio-coverage">Carregando eventos financeiros…</p> : eventSummary.isError ? <p role="alert" className="portfolio-coverage">Não foi possível carregar os eventos financeiros.</p> : eventSummary.data && <>
        <div className="portfolio-lifetime-totals financial-event-totals">
          <div><span>Aportes externos</span><strong>{money(eventSummary.data.contributions)}</strong></div>
          <div><span>Retiradas externas</span><strong>{money(eventSummary.data.withdrawals)}</strong></div>
          <div><span>Fluxo líquido externo</span><strong>{money(eventSummary.data.net_external_cash_flow)}</strong></div>
          <div><span>Dividendos recebidos informados</span><strong>{money(eventSummary.data.dividends_received)}</strong></div>
          <div><span>JCP recebido informado</span><strong>{money(eventSummary.data.jcp_received)}</strong></div>
        </div>
        <p className="portfolio-coverage">Proventos são separados de aportes. Se reinvestidos, a compra permanece como operação distinta; o sistema não soma proventos como novo dinheiro externo.</p>
      </>}
    </article>}
    <article className="panel composition-panel">
      <div className="panel-heading"><div><h3>Composição atual disponível</h3><p>Valores por base registrada · data-base {composition?.as_of ? new Date(`${composition.as_of}T12:00:00`).toLocaleDateString('pt-BR') : '—'}</p></div><span className="tag">{composition?.coverage === 'partial' ? 'Cobertura parcial' : 'Privado'}</span></div>
      {performance.isLoading ? <p role="status" className="empty compact">Carregando composição…</p> : performance.isError ? <p role="alert" className="empty compact">Não foi possível carregar a composição da carteira.</p> : composition && <>
        {composition.missing_components.length > 0 && <p className="portfolio-coverage">Dados ausentes: {composition.missing_components.join('; ')}. Valores de mercado das ações indisponíveis.</p>}
        <div className="portfolio-applied-capital"><div><span>Capital aplicado contabilizado em posições abertas</span><strong>{money(appliedCapital)}</strong></div><ul><li><span>Ações · custo aberto com taxas</span><strong>{money(equityCapital)} · {equityShare == null ? '—' : `${equityShare.replace('.', ',')}%`}</strong></li><li><span>CDB · principal efetivo</span><strong>{money(fixedCapital)} · {fixedShare == null ? '—' : `${fixedShare.replace('.', ',')}%`}</strong></li></ul><p>Posições CDB informadas manualmente ficam separadas e não entram neste total. Ações são avaliadas pelo custo de aquisição, não por cotação atual.</p></div>
        <div className="portfolio-composition-charts">
          <div className="portfolio-asset-charts" aria-label="Composição por classe de ativo">
            <AssetDonut title="Ações · custo aberto" items={composition.equities} totalValue={composition.class_totals.equities_open_cost}/>
            <AssetDonut title="Renda fixa · principal efetivo" items={composition.fixed_income} totalValue={composition.class_totals.fixed_income_open_principal}/>
          </div>
          <div className="portfolio-basis-chart"><h4>Bases disponíveis · sem total agregado</h4><p>Posições declaradas permanecem em série separada.</p><div className="portfolio-basis-chart-canvas"><ResponsiveContainer width="100%" height="100%"><BarChart data={[
            { name: 'Ações · custo aberto', value: Number(composition.class_totals.equities_open_cost) },
            { name: 'RF · principal ledger', value: Number(composition.class_totals.fixed_income_open_principal) },
            { name: 'Observações declaradas', value: Number(composition.class_totals.declared_positions) },
          ]} layout="vertical" margin={{ left: 14, right: 18 }}><XAxis type="number" hide/><YAxis type="category" dataKey="name" width={138} tick={{ fill: '#a9bac2', fontSize: 10 }}/><Tooltip formatter={value => money(String(value))}/><Bar dataKey="value" fill="#68e5b4" radius={[0, 5, 5, 0]}>{[0, 1, 2].map(index => <Cell key={index} fill={['#8298f8', '#68e5b4', '#e8c77c'][index]}/>)}</Bar></BarChart></ResponsiveContainer></div></div>
        </div>
        <h4>Renda variável · custo de aquisição aberto</h4><PositionList items={composition.equities}/>
        <h4>Renda fixa · principal efetivo aberto</h4><PositionList items={composition.fixed_income}/>
        <h4>Posições declaradas · observações separadas</h4><PositionList items={composition.declared_positions}/>
        {composition.missing_fixed_income.length > 0 && <p className="portfolio-coverage">Sem valor disponível: {composition.missing_fixed_income.join(', ')}.</p>}
        <p className="portfolio-coverage">Estimativas brutas e líquidas de CDB são calculadas por contrato com premissas explícitas; elas não são somadas a este principal.</p>
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
