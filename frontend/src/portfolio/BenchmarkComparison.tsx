import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { ChartNoAxesCombined } from 'lucide-react'
import './portfolio.css'

const names = { CDI: 'CDI · taxa diária acumulada', IBOVESPA: 'Ibovespa · índice de preços', IPCA: 'IPCA · inflação mensal' }
const statusText = {
  feature_disabled: 'Histórico da Brapi desativado. Habilite a configuração existente de histórico individual de ações para consultar o Ibovespa.',
  provider_not_configured: 'Configure o token Brapi no backend para consultar o Ibovespa.',
  provider_unavailable: 'Uma das fontes gratuitas está indisponível ou limitou a consulta. Tente novamente mais tarde.',
  source_coverage: 'As fontes retornaram cobertura parcial. O gráfico mostra apenas meses completos comuns às três séries.',
  incompatible_data: 'As unidades ou séries retornadas não são compatíveis; os valores não foram comparados.',
  insufficient_common_period: 'Ainda não há dois meses completos em comum entre CDI, Ibovespa e IPCA.',
} as const

export function BenchmarkComparison({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [period, setPeriod] = useState<'1M' | '3M'>('3M')
  const query = useQuery({ queryKey: ['benchmark-comparison', identity, period], queryFn: ({ signal }) => repository.benchmarks(period, signal), retry: false })
  const data = query.data
  const chart = data?.points?.map(point => ({
    month: point.month,
    CDI: Number(point.values.CDI),
    IBOVESPA: Number(point.values.IBOVESPA),
    IPCA: Number(point.values.IPCA),
    exact: point.values,
  })) ?? []
  return <article className="panel benchmark-comparison" aria-label="Comparação de indicadores de referência">
    <div className="panel-heading"><div><h3>Indicadores de referência</h3><p>Base 100 no primeiro mês comum · não representa retorno da carteira</p></div><ChartNoAxesCombined size={18}/></div>
    <div className="periods benchmark-periods" aria-label="Período da comparação">{(['1M', '3M'] as const).map(value => <button type="button" key={value} aria-pressed={period === value} className={period === value ? 'selected' : ''} onClick={() => setPeriod(value)}>{value}</button>)}</div>
    {query.isLoading ? <p role="status" className="empty compact">Carregando séries de referência…</p>
      : query.isError ? <div role="alert" className="empty compact">Não foi possível carregar os indicadores. <button type="button" onClick={() => void query.refetch()}>Tentar novamente</button></div>
        : !data || data.availability === 'disabled' || data.availability === 'unavailable' || data.availability === 'empty' || chart.length < 2
          ? <div role="status" className="empty compact"><h4>{data?.availability === 'empty' ? 'Sem janela comum suficiente' : 'Indicadores indisponíveis'}</h4><p>{data?.reason ? statusText[data.reason] : 'As séries gratuitas não estão disponíveis nesta configuração.'}</p></div>
          : <>
            {data.availability === 'partial' && <p role="status" className="portfolio-coverage">{statusText.source_coverage} {data.coverage_start && data.coverage_end ? `${new Date(`${data.coverage_start}T12:00:00`).toLocaleDateString('pt-BR')} a ${new Date(`${data.coverage_end}T12:00:00`).toLocaleDateString('pt-BR')}.` : ''}</p>}
            <div className="benchmark-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chart} margin={{ top: 14, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="month" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/><YAxis domain={['auto', 'auto']} tickFormatter={value => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} axisLine={false} tickLine={false}/>
              <Tooltip labelFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })} formatter={(_value, name, item) => [`${Number(item.payload.exact[String(name)]).toLocaleString('pt-BR', { maximumFractionDigits: 3 })}`, names[String(name) as keyof typeof names] ?? String(name)]}/><Legend formatter={value => names[String(value) as keyof typeof names] ?? String(value)}/>
              <Line type="monotone" dataKey="CDI" stroke="#68e5b4" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false}/><Line type="monotone" dataKey="IBOVESPA" stroke="#8298f8" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false}/><Line type="monotone" dataKey="IPCA" stroke="#e8c77c" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false}/>
            </LineChart></ResponsiveContainer></div>
            <div className="benchmark-notes"><span>Fonte: {data.source}</span><span>Ibovespa: índice de preços, sem proventos</span><span>Período comum: {data.coverage_start} a {data.coverage_end}</span></div>
          </>}
  </article>
}
