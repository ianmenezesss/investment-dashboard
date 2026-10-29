import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Decimal from 'decimal.js'
import type { EquityComparison as ComparisonData, IndividualEquityPriceHistory } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import './portfolio.css'

const periods: { value: IndividualEquityPriceHistory['period']; label: string }[] = [
  { value: '1M', label: '1M' }, { value: '3M', label: '3M' }, { value: '6M', label: '6M' },
  { value: '1A', label: '1A' }, { value: 'MAX', label: 'Máximo' },
]
const colors = ['#68e5b4', '#8298f8', '#e8c77c', '#d494dc']
const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')

const reasonMessages: Record<NonNullable<ComparisonData['reason']>, string> = {
  feature_disabled: 'A comparação está desativada. Nenhuma fonte externa foi habilitada.',
  provider_not_configured: 'A comparação ficará disponível após validar uma fonte histórica e sua licença.',
  provider_unavailable: 'A fonte de histórico está temporariamente indisponível. Tente novamente mais tarde.',
  ticker_not_found: 'A fonte não possui histórico para um dos ativos selecionados.',
  invalid_provider_response: 'A fonte retornou dados inválidos. Nenhum preço foi exibido.',
  incompatible_data: 'Os ativos não têm moeda, fonte ou base de preço compatíveis para comparação.',
  no_common_date: 'Não há uma data com fechamento válido para todos os ativos selecionados.',
  empty_history: 'A fonte não retornou fechamentos diários para um dos ativos neste período.',
}

const decimalString = (value: unknown) => {
  if (typeof value !== 'string' || !/^\d+(?:\.\d{1,28})?$/.test(value)) return false
  try { return new Decimal(value).isFinite() && new Decimal(value).isPositive() } catch { return false }
}

export function isEquityComparisonContract(value: unknown): value is ComparisonData {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ComparisonData>
  if (!Array.isArray(candidate.tickers) || candidate.tickers.length < 2 || candidate.tickers.length > 4
    || !['1M', '3M', '6M', '1A', 'MAX'].includes(candidate.period ?? '')
    || !['available', 'disabled', 'unavailable', 'empty'].includes(candidate.availability ?? '')
    || !Array.isArray(candidate.points) || !Array.isArray(candidate.coverage)) return false
  const dates = candidate.points.map(point => point?.date)
  if (dates.some(date => typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date))
    || dates.some((date, index) => index > 0 && date! <= dates[index - 1]!)) return false
  if (!candidate.points.every(point => point.values && typeof point.values === 'object'
    && Object.keys(point.values).length === candidate.tickers!.length
    && candidate.tickers!.every(ticker => point.values[ticker] === null || decimalString(point.values[ticker])))) return false
  if (candidate.availability !== 'available') return candidate.points.length === 0 && candidate.coverage.length === 0
    && candidate.common_start_date === null
  if (!candidate.currency || !candidate.source || !candidate.price_basis || candidate.price_basis === 'unknown'
    || !candidate.common_start_date || !candidate.points.length
    || candidate.points[0].date !== candidate.common_start_date
    || candidate.coverage.length !== candidate.tickers.length) return false
  const firstPoint = candidate.points[0]
  const selectedTickers = candidate.tickers
  if (!candidate.coverage.every((item, index) => item.ticker === candidate.tickers![index]
    && typeof item.coverage_start === 'string' && typeof item.coverage_end === 'string' && decimalString(item.base_price))) return false
  return selectedTickers.every(ticker => firstPoint.values[ticker] === '100')
}

export function prepareComparisonChartData(data: ComparisonData) {
  return data.points.map(point => ({
    date: point.date,
    ...Object.fromEntries(data.tickers.map(ticker => [ticker,
      point.values[ticker] === null ? null : Number(point.values[ticker]),
    ])),
  }))
}

function formatChange(indexValue: string) {
  const change = new Decimal(indexValue).minus(100)
  const formatted = Number(change.toFixed(2)).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${formatted}%`
}

export function AssetComparison({ repository, identity, tickers }: {
  repository: PrivateRepository
  identity: string
  tickers: string[]
}) {
  const signature = tickers.join(',')
  const availableTickers = useMemo(() => [...new Set(tickers)].sort(), [signature])
  const [selected, setSelected] = useState<string[]>(() => availableTickers.slice(0, 2))
  const [period, setPeriod] = useState<IndividualEquityPriceHistory['period']>('1M')

  useEffect(() => {
    setSelected(current => {
      const retained = current.filter(ticker => availableTickers.includes(ticker)).slice(0, 4)
      return retained.length >= 2 ? retained : [...retained, ...availableTickers.filter(ticker => !retained.includes(ticker))].slice(0, 2)
    })
  }, [signature])

  const history = useQuery({
    queryKey: ['equity-comparison', identity, selected, period],
    queryFn: ({ signal }) => repository.equityComparison(selected, period, signal),
    enabled: selected.length >= 2 && selected.length <= 4,
    retry: false,
  })
  const data = history.data
  const validData = isEquityComparisonContract(data)
  const chartData = useMemo(() => validData ? prepareComparisonChartData(data) : [], [data, validData])
  const showChart = validData && data.availability === 'available' && chartData.length > 0

  function toggleTicker(ticker: string) {
    setSelected(current => current.includes(ticker)
      ? current.filter(item => item !== ticker)
      : current.length < 4 ? [...current, ticker] : current)
  }

  return <article className="panel equity-comparison" aria-label="Comparação da evolução dos ativos">
    <div className="panel-heading">
      <div><h3>Comparar ativos</h3><p>Variação de preço com base 100 na primeira data comum</p></div>
      <span className="tag">2 a 4 ações</span>
    </div>
    <fieldset className="equity-comparison-assets">
      <legend>Selecione de 2 a 4 ativos da carteira</legend>
      {availableTickers.length === 0 ? <p>Nenhuma ação em carteira.</p> : availableTickers.map(ticker => <label key={ticker}>
        <input type="checkbox" checked={selected.includes(ticker)} disabled={!selected.includes(ticker) && selected.length >= 4}
          onChange={() => toggleTicker(ticker)}/>{ticker}
      </label>)}
    </fieldset>
    <div className="periods equity-comparison-periods" aria-label="Período da comparação">
      {periods.map(item => <button key={item.value} type="button" aria-pressed={period === item.value}
        className={period === item.value ? 'selected' : ''} onClick={() => setPeriod(item.value)}>{item.label}</button>)}
    </div>
    {selected.length < 2 ? <div className="empty compact equity-comparison-state" role="status">
      <h4>Selecione pelo menos duas ações</h4><p>Escolha de 2 a 4 posições abertas para comparar.</p>
    </div> : history.isLoading ? <p className="empty compact equity-comparison-state" role="status">Carregando comparação…</p>
      : history.isError ? <div className="empty compact equity-comparison-state" role="alert">
        <h4>Não foi possível carregar a comparação</h4>
        <p>{history.error instanceof Error ? history.error.message : 'Ocorreu um erro ao consultar o histórico.'}</p>
        <button type="button" onClick={() => void history.refetch()}>Tentar novamente</button>
      </div> : !validData ? <div className="empty compact equity-comparison-state" role="alert">
        <h4>Resposta de comparação inválida</h4><p>Nenhum preço foi exibido.</p>
      </div> : data.availability !== 'available' ? <div className="empty compact equity-comparison-state" role="status">
        <h4>{data.availability === 'empty' ? 'Sem dados compatíveis' : 'Comparação indisponível'}</h4>
        <p>{data.reason ? reasonMessages[data.reason] : 'Não há uma série de preços disponível.'}</p>
      </div> : showChart ? <>
        <div className="equity-comparison-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 15, right: 20, left: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/>
          <XAxis dataKey="date" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/>
          <YAxis tickFormatter={value => `${(Number(value) - 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`} axisLine={false} tickLine={false} width={60}/>
          <Tooltip labelFormatter={value => dateLabel(String(value))} formatter={(value, name) => value === null
            ? ['Sem fechamento nesta data', String(name)]
            : [formatChange(String(value)), String(name)]}/>
          {data.tickers.map((ticker, index) => <Line key={ticker} type="linear" dataKey={ticker} name={ticker}
            stroke={colors[index % colors.length]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} connectNulls={false}/>) }
        </LineChart></ResponsiveContainer></div>
        <ul className="equity-comparison-legend">
          {data.coverage.map((item, index) => <li key={item.ticker}>
            <span><i style={{ background: colors[index % colors.length] }}/><strong>{item.ticker}</strong></span>
            <small>Base {item.base_price} · {dateLabel(item.coverage_start)} a {dateLabel(item.coverage_end)}</small>
          </li>)}
        </ul>
        <div className="equity-comparison-footer">
          <span>Base comum: {dateLabel(data.common_start_date!)}</span>
          <span>Moeda: {data.currency}</span>
          <span>Fonte: {data.source}</span>
          <span>Base do preço: {data.price_basis === 'raw_close' ? 'fechamento sem ajustes' : 'fechamento ajustado'}</span>
        </div>
        <p className="equity-comparison-note">Índice base 100 mostra variação do preço desde a data comum; não representa retorno total nem inclui proventos.</p>
      </> : null}
  </article>
}
