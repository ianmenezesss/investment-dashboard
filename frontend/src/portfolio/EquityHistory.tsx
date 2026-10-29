import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Decimal from 'decimal.js'
import type { EquityHistory as EquityHistoryData } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { formatFlowAxisTick } from './format'
import './portfolio.css'

const periods = ['1M', '3M', '6M', '1A', 'Tudo']
export function formatEquityMoney(value: string | number): string {
  const [integer, fraction] = new Decimal(String(value)).toDecimalPlaces(2).toFixed(2).split('.')
  return `R$\u00a0${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}`
}
const dayLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')
export function equityHistoryTooltip(value: unknown, name: string): [string, string] {
  const title = name === 'market_value' ? 'Valor de mercado das ações' : 'Fluxo líquido em ações'
  return [value == null ? 'Indisponível' : formatEquityMoney(String(value)), title]
}
export function prepareEquityChartData(points: EquityHistoryData['points']) {
  return points.map(point => ({
    ...point,
    market_value_plot: point.market_value === null ? null : Number(point.market_value),
    net_invested_plot: Number(point.net_invested),
  }))
}

export function EquityHistory({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [period, setPeriod] = useState('Tudo')
  const history = useQuery({ queryKey: ['equity-history', identity, period], queryFn: ({ signal }) => repository.equityHistory(period, signal), retry: false })
  const data = history.data
  const latest = data?.points.at(-1)
  const pricedPoints = data?.points.filter(point => point.market_value !== null) ?? []
  const chartData = data ? prepareEquityChartData(data.points) : []
  const deltaPoint = [...pricedPoints].reverse().find(point => point.difference_over_net_flows !== null)
  const delta = deltaPoint?.difference_over_net_flows
  const providerReasons = Object.values(data?.provider_errors ?? {})
  const providerMessage = providerReasons.includes('missing_token') ? 'Configure o acesso à fonte de cotações no backend para consultar preços históricos.'
    : providerReasons.includes('disabled') ? 'O serviço de cotações está desabilitado na configuração do backend.'
      : providerReasons.includes('raw_price_unavailable') ? 'A fonte não forneceu fechamentos originais. O histórico de valor exige acesso a rawClose no plano habilitado.'
        : providerReasons.some(reason => ['provider_timeout', 'provider_unavailable', 'provider_http_error', 'rate_limited'].includes(reason))
          ? 'A fonte de cotações está indisponível ou limitou a consulta. Tente novamente mais tarde.'
          : 'Não há preços históricos originais disponíveis para os ativos e período selecionados.'

  return <article className="panel equity-history" aria-label="Histórico do valor de mercado das ações">
    <div className="panel-heading">
      <div><h3>Evolução histórica das ações · estimativa externa</h3><p>Fechamento por pregão e quantidades reconstruídas pelas operações registradas</p></div>
      <div className="periods">{periods.map(value => <button key={value} aria-pressed={period === value} className={period === value ? 'selected' : ''} onClick={() => setPeriod(value)}>{value}</button>)}</div>
    </div>
    {history.isLoading ? <p role="status" className="empty compact">Carregando histórico de ações…</p>
      : history.isError ? <p role="alert" className="empty compact">Não foi possível carregar o histórico de ações. Tente novamente mais tarde.</p>
      : !data?.points.length ? <div className="empty compact"><h4>{data?.coverage === 'empty' ? 'Sem operações de ações registradas' : 'Histórico de preços indisponível'}</h4>
        <p>{providerMessage}</p>
      </div>
      : <>
        {providerReasons.length > 0 && <p className="portfolio-coverage" role="status">{providerMessage}</p>}
        {(data.coverage === 'partial' || latest?.coverage === 'partial') && <p className="portfolio-coverage" role="status">Cobertura parcial{data.missing_tickers.length ? ` · sem preço para ${data.missing_tickers.join(', ')}` : ''}. Valores ausentes permanecem indisponíveis.</p>}
        <div className="equity-history-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 16, right: 18, left: 5, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/>
          <XAxis dataKey="date" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/>
          <YAxis tickFormatter={formatFlowAxisTick} axisLine={false} tickLine={false}/>
          <Tooltip labelFormatter={value => dayLabel(String(value))} formatter={(_value, name, item) => equityHistoryTooltip(
            String(name) === 'market_value' ? item.payload.market_value : item.payload.net_invested, String(name))}/>
          <Line type="monotone" dataKey="market_value_plot" name="market_value" stroke="#68e5b4" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/>
          <Line type="stepAfter" dataKey="net_invested_plot" name="net_invested" stroke="#8298f8" strokeWidth={1.5} dot={false} isAnimationActive={false}/>
        </LineChart></ResponsiveContainer></div>
        <div className="equity-history-legend"><span><i className="market"/>Valor de mercado das ações</span><span><i className="flow"/>Fluxo líquido em ações</span></div>
        <div className="equity-history-summary">
          <span>Valor de mercado mais recente<strong>{latest?.market_value == null ? 'Indisponível' : formatEquityMoney(latest.market_value)}</strong></span>
          <span>Fluxo líquido acumulado em ações<strong>{latest ? formatEquityMoney(latest.net_invested) : 'Indisponível'}</strong></span>
          <span>Mercado menos fluxo líquido no pregão de {deltaPoint ? dayLabel(deltaPoint.date) : 'referência'}<strong>{delta == null ? 'Indisponível' : formatEquityMoney(delta)}</strong></span>
        </div>
        <p className="equity-history-note">Preços históricos estimados por fonte externa; confira os valores na corretora. Diferença não é rentabilidade nem lucro realizado. Exclui caixa, proventos, tributos e operações não registradas. Fechamento bruto da brapi; não é cotação em tempo real.</p>
        <div className="chart-footer">Fonte: brapi · preço sem ajuste · pregões retornados pela fonte, sem preencher lacunas <span>{data.coverage_start && data.coverage_end ? `Pregões disponíveis: ${dayLabel(data.coverage_start)} a ${dayLabel(data.coverage_end)} · janela solicitada ${dayLabel(data.period_start)} a ${dayLabel(data.period_end)}` : 'Cobertura indisponível'}</span></div>
      </>}
  </article>
}
