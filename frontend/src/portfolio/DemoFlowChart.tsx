import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartNoAxesCombined } from 'lucide-react'
import { formatFlowAxisTick } from './format'

type Point = { date: string; value: number }

export function DemoFlowChart({ period, onPeriodChange, series }: {
  period: string
  onPeriodChange: (period: string) => void
  series: Point[]
}) {
  return <article className="panel evolution">
    <div className="panel-heading"><div><h3>Fluxo acumulado de operações</h3><p>Compras menos vendas, sem taxas · não representa rentabilidade</p></div><div className="periods">{['1M', '3M', '6M', '1A', 'Tudo'].map(value => <button aria-pressed={period === value} className={period === value ? 'selected' : ''} key={value} onClick={() => onPeriodChange(value)}>{value}</button>)}</div></div>
    {series.length ? <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={series} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}><defs><linearGradient id="green" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#65e3b2" stopOpacity={0.22}/><stop offset="100%" stopColor="#65e3b2" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="date" tickFormatter={value => new Date(value + 'T12:00:00').toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false} tick={{ fill: '#7e8b96', fontSize: 11 }} dy={12}/><YAxis tickFormatter={formatFlowAxisTick} axisLine={false} tickLine={false} tick={{ fill: '#7e8b96', fontSize: 11 }}/><Tooltip contentStyle={{ background: '#151e25', border: '1px solid #33414c', borderRadius: 10 }} formatter={value => [Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }), 'Fluxo acumulado']} labelFormatter={value => new Date(value + 'T12:00:00').toLocaleDateString('pt-BR')}/><Area type="stepAfter" dataKey="value" stroke="#65e3b2" strokeWidth={2.5} fill="url(#green)"/></AreaChart></ResponsiveContainer></div> : <div className="empty"><ChartNoAxesCombined/><h4>Sua história começa no primeiro aporte</h4><p>Registre uma operação ou explore os dados de demonstração.</p></div>}
    <div className="chart-footer"><span className="legend-dot"/> Fluxo das operações <span>Sem comparação com índices</span></div>
  </article>
}
