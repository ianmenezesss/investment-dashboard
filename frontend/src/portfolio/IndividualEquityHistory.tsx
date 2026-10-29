import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Decimal from 'decimal.js'
import type { IndividualEquityPriceHistory as HistoryData } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import './portfolio.css'

const periods: { value: HistoryData['period']; label: string }[] = [
  { value: '1M', label: '1M' }, { value: '3M', label: '3M' }, { value: '6M', label: '6M' },
  { value: '1A', label: '1A' }, { value: 'MAX', label: 'Máximo' },
]

export function formatDailyPrice(value: string, currency = 'BRL') {
  const amount = new Decimal(value)
  const fixed = amount.toFixed(8).replace(/(?:\.0+|(?:(\.\d*?)0+))$/, '$1')
  const [integer, fraction = ''] = fixed.split('.')
  const grouped = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(BigInt(integer))
  return `${currency === 'BRL' ? 'R$\u00a0' : `${currency}\u00a0`}${grouped},${fraction.padEnd(2, '0')}`
}

const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')
const unavailableMessage: Record<NonNullable<HistoryData['reason']>, string> = {
  feature_disabled: 'O histórico individual está desativado. Nenhuma fonte externa foi habilitada.',
  provider_not_configured: 'O histórico está indisponível enquanto uma fonte de dados e sua licença não forem validadas.',
  provider_unavailable: 'A fonte de histórico está temporariamente indisponível. Tente novamente mais tarde.',
  ticker_not_found: 'A fonte não possui histórico disponível para este ativo.',
  invalid_provider_response: 'A fonte retornou dados inválidos. Nenhum preço foi exibido.',
}

export function preparePriceChartData(points: HistoryData['points']) {
  return points.map(point => ({ ...point, close_plot: Number(point.close) })).sort((a, b) => a.date.localeCompare(b.date))
}

export function isPriceHistoryContract(value: unknown): value is HistoryData {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<HistoryData>
  const validPoints = Array.isArray(candidate.points) && candidate.points.every(point => {
    if (!point || typeof point.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(point.date)
      || typeof point.close !== 'string' || !/^\d+(?:\.\d{1,8})?$/.test(point.close)) return false
    try { return new Decimal(point.close).isFinite() && new Decimal(point.close).isPositive() } catch { return false }
  })
  return typeof candidate.ticker === 'string'
    && ['1M', '3M', '6M', '1A', 'MAX'].includes(candidate.period ?? '')
    && typeof candidate.currency === 'string'
    && (candidate.source === null || typeof candidate.source === 'string')
    && ['raw_close', 'adjusted_close', 'unknown'].includes(candidate.price_basis ?? '')
    && typeof candidate.period_end === 'string'
    && ['available', 'disabled', 'unavailable', 'empty'].includes(candidate.availability ?? '')
    && validPoints
}

export function IndividualEquityHistory({ repository, identity, tickers }: {
  repository: PrivateRepository
  identity: string
  tickers: string[]
}) {
  const availableTickers = useMemo(() => [...new Set(tickers)].sort(), [tickers])
  const tickerSignature = availableTickers.join(',')
  const [ticker, setTicker] = useState(availableTickers[0] ?? '')
  const [period, setPeriod] = useState<HistoryData['period']>('1M')
  useEffect(() => {
    if (!availableTickers.includes(ticker)) setTicker(availableTickers[0] ?? '')
  }, [tickerSignature, ticker, availableTickers])
  const history = useQuery({
    queryKey: ['individual-equity-price-history', identity, ticker, period],
    queryFn: ({ signal }) => repository.equityPriceHistory(ticker, period, signal),
    enabled: availableTickers.length > 0 && !!ticker,
    retry: false,
  })
  const data = history.data
  const validData = isPriceHistoryContract(data)
  const chartData = useMemo(() => validData ? preparePriceChartData(data.points) : [], [data, validData])
  const showChart = validData && data.availability === 'available' && chartData.length > 0

  return <article className="panel individual-equity-history" aria-label="Histórico individual de preços das ações">
    <div className="panel-heading">
      <div><h3>Histórico de preço por ação</h3><p>Fechamentos diários fornecidos por uma fonte validada</p></div>
      {availableTickers.length > 0 && <label className="individual-history-ticker">Ativo
        <select aria-label="Selecionar ativo para histórico" value={ticker} onChange={event => setTicker(event.target.value)}>
          {availableTickers.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>}
    </div>
    <div className="periods individual-history-periods" aria-label="Período do histórico">
      {periods.map(item => <button key={item.value} type="button" aria-pressed={period === item.value}
        className={period === item.value ? 'selected' : ''} onClick={() => setPeriod(item.value)}>{item.label}</button>)}
    </div>
    {availableTickers.length === 0 ? <div className="empty compact individual-history-state">
      <h4>Nenhuma ação em carteira</h4><p>Registre uma posição em ações para selecionar um ativo.</p>
    </div> : history.isLoading ? <p className="empty compact individual-history-state" role="status">Carregando histórico de {ticker}…</p>
      : history.isError ? <div className="empty compact individual-history-state" role="alert">
        <h4>Não foi possível carregar o histórico</h4><p>{history.error instanceof Error ? history.error.message : 'Ocorreu um erro ao consultar o histórico.'}</p>
        <button type="button" onClick={() => void history.refetch()}>Tentar novamente</button>
      </div> : !validData ? <div className="empty compact individual-history-state" role="alert">
        <h4>Resposta de histórico inválida</h4><p>Nenhum preço foi exibido. Tente novamente mais tarde.</p>
      </div> : data.availability === 'disabled' || data.availability === 'unavailable' ? <div className="empty compact individual-history-state" role="status">
        <h4>Histórico indisponível</h4><p>{data.reason ? unavailableMessage[data.reason] : 'Não há uma fonte disponível para este histórico.'}</p>
      </div> : data.availability === 'empty' || !data.points.length ? <div className="empty compact individual-history-state" role="status">
        <h4>Sem preços para o período</h4><p>A fonte não retornou fechamentos diários neste intervalo.</p>
      </div> : showChart ? <>
        <div className="individual-history-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 15, right: 20, left: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/>
          <XAxis dataKey="date" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/>
          <YAxis tickFormatter={value => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} axisLine={false} tickLine={false} width={54}/>
          <Tooltip labelFormatter={value => dateLabel(String(value))} formatter={(_value, _name, item) => [formatDailyPrice(String(item.payload.close), data.currency), `Fechamento de ${ticker}`]}/>
          <Line type="monotone" dataKey="close_plot" name="close" stroke="#68e5b4" strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false}/>
        </LineChart></ResponsiveContainer></div>
        <div className="individual-history-footer">
          <span>Base: {data.price_basis === 'raw_close' ? 'fechamento sem ajustes' : data.price_basis === 'adjusted_close' ? 'fechamento ajustado' : 'não informada'}</span>
          <span>{data.source ? `Fonte: ${data.source}` : 'Fonte não informada'}</span>
          <span>{data.coverage_start && data.coverage_end ? `Pregões disponíveis: ${dateLabel(data.coverage_start)} a ${dateLabel(data.coverage_end)}` : 'Cobertura indisponível'}</span>
        </div>
      </> : null}
  </article>
}
