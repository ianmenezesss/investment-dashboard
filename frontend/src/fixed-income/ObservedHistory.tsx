import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScatterChart, Scatter, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { marketMoney } from '../components/market-format'

export type ObservedSeries = { coverage: string; warning: string; points: { as_of: string; gross_value: string; net_value: string; source: string }[] }
export function ObservedHistory({ id, identity, load }: { id: number; identity: string; load: (id: number, start: string, end: string, signal: AbortSignal) => Promise<ObservedSeries> }) {
  const [period, setPeriod] = useState(0)
  const end = new Date().toLocaleDateString('en-CA')
  const cutoff = new Date(end + 'T12:00:00'); cutoff.setMonth(cutoff.getMonth() - (period || 120))
  const start = cutoff.toLocaleDateString('en-CA')
  const query = useQuery({ queryKey: ['fixed-income', identity, 'observed-history', id, start, end], queryFn: async ({ signal }) => {
    const response = await load(id, start, end, signal)
    if (!response || !Array.isArray(response.points)) throw new Error('Resposta inválida do histórico de posições observadas.')
    return response
  }, retry: false })
  return <article className="panel fi-section" aria-label="Evolução das posições observadas"><h3>Evolução das posições observadas</h3><p>Valores declarados do CDB inteiro. Aportes e rendimentos não são deduzidos da variação entre pontos. Sem interpolação ou soma com lotes.</p><div className="periods">{[[1,'1M'],[3,'3M'],[6,'6M'],[12,'1A'],[0,'Até 10 anos']].map(([value,label]) => <button key={value} aria-pressed={period === value} onClick={() => setPeriod(Number(value))}>{label}</button>)}</div>
    {query.isPending && <p role="status">Carregando posições observadas…</p>}
    {query.isError && <p role="alert">Não foi possível carregar as posições. <button onClick={() => void query.refetch()}>Tentar novamente</button></p>}
    {query.data && !query.data.points.length && <p>Nenhuma posição observada neste período. Histórico patrimonial indisponível.</p>}
    {!!query.data?.points.length && <><p>Cobertura pontual: {query.data.points[0].as_of} a {query.data.points.at(-1)!.as_of}. Datas intermediárias sem avaliação.</p><div style={{ width: '100%', height: 280 }}><ResponsiveContainer><ScatterChart><CartesianGrid stroke="#33414c"/><XAxis type="number" dataKey="day" domain={['dataMin','dataMax']} tickFormatter={v => new Date(v).toLocaleDateString('pt-BR')}/><YAxis dataKey="value" tickFormatter={v => marketMoney(v)}/><Tooltip formatter={v => marketMoney(String(v))} labelFormatter={v => new Date(Number(v)).toLocaleDateString('pt-BR')} contentStyle={{ background: '#151e25' }}/><Scatter name="Bruto observado" fill="#65e3b2" data={query.data.points.map(p => ({ day: Date.parse(p.as_of + 'T12:00:00'), value: Number(p.gross_value) }))}/></ScatterChart></ResponsiveContainer></div><details><summary>Consultar valores e fontes</summary><ul>{query.data.points.map(p => <li key={p.as_of}>{p.as_of}: bruto {marketMoney(p.gross_value)}, líquido {marketMoney(p.net_value)} · {p.source}</li>)}</ul></details></>}
  </article>
}
