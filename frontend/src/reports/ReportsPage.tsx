import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Decimal from 'decimal.js'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { aggregateContributions, contributionRows, decimalMoney } from './contributions'
import './reports.css'

const today = () => new Date().toLocaleDateString('en-CA')
const thisYear = () => `${today().slice(0, 4)}-01-01`
const chartMoney = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value)

export function ReportsPage({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [start, setStart] = useState(thisYear)
  const [end, setEnd] = useState(today)
  const [bucket, setBucket] = useState<'month' | 'year'>('month')
  const query = useQuery({ queryKey: ['reports-movements', identity], queryFn: ({ signal }) => repository.movements(signal), retry: false })
  const rows = useMemo(() => contributionRows(query.data ?? [], start, end), [query.data, start, end])
  const monthly = useMemo(() => aggregateContributions(rows, 'month'), [rows])
  const yearly = useMemo(() => aggregateContributions(rows, 'year'), [rows])
  const chartRows = bucket === 'month' ? monthly : yearly
  const equities = rows.filter(row => row.operation === 'BUY').reduce((sum, row) => sum.plus(row.financial_value ?? '0').plus(row.fees ?? '0'), new Decimal(0))
  const fixed = rows.filter(row => row.operation === 'APPLICATION').reduce((sum, row) => sum.plus(row.financial_value ?? '0'), new Decimal(0))
  const total = equities.plus(fixed)
  return <section className="reports-page" aria-label="Relatórios financeiros">
    <article className="panel reports-panel">
      <div className="panel-heading"><div><h2>Relatório de aportes</h2><p>Compras de ações incluem taxas; renda fixa considera principal aplicado. Valores registrados, sem rentabilidade ou valor de mercado.</p></div></div>
      <div className="reports-filters">
        <label>De<input type="date" aria-label="Data inicial do relatório" value={start} max={end || undefined} onChange={event => setStart(event.target.value)}/></label>
        <label>Até<input type="date" aria-label="Data final do relatório" value={end} min={start || undefined} max={today()} onChange={event => setEnd(event.target.value)}/></label>
        <div className="periods" aria-label="Agrupar aportes por período"><button type="button" aria-pressed={bucket === 'month'} className={bucket === 'month' ? 'selected' : ''} onClick={() => setBucket('month')}>Mês</button><button type="button" aria-pressed={bucket === 'year'} className={bucket === 'year' ? 'selected' : ''} onClick={() => setBucket('year')}>Ano</button></div>
      </div>
      {query.isPending ? <p role="status" className="reports-state">Carregando movimentações privadas…</p> : query.isError ? <div role="alert" className="reports-state">Não foi possível carregar os dados do relatório. <button type="button" onClick={() => { void query.refetch() }}>Tentar novamente</button></div> : <>
        <div className="reports-summary"><div><span>Total aportado no período</span><strong>{decimalMoney(total)}</strong></div><div><span>Ações · compras com taxas</span><strong>{decimalMoney(equities)}</strong></div><div><span>Renda fixa · principal aplicado</span><strong>{decimalMoney(fixed)}</strong></div><div><span>Registros de aporte</span><strong>{rows.length}</strong></div></div>
        {chartRows.length ? <div className="reports-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartRows.map(row => ({ ...row, equitiesValue: row.equities.toNumber(), fixedValue: row.fixedIncome.toNumber() }))} margin={{ top: 10, right: 12, left: 12, bottom: 6 }}>
          <CartesianGrid vertical={false} stroke="#25313a" strokeDasharray="3 5"/><XAxis dataKey="key" tick={{ fill: '#9aabb4', fontSize: 11 }}/><YAxis tickFormatter={chartMoney} tick={{ fill: '#9aabb4', fontSize: 10 }}/><Tooltip formatter={(value, name) => [chartMoney(Number(value)), name === 'equitiesValue' ? 'Ações' : 'Renda fixa']}/><Legend formatter={name => name === 'equitiesValue' ? 'Ações · compras com taxas' : 'Renda fixa · principal'}/><Bar dataKey="equitiesValue" stackId="aporte" fill="#8298f8" radius={[0, 0, 0, 0]}/><Bar dataKey="fixedValue" stackId="aporte" fill="#68e5b4" radius={[4, 4, 0, 0]}/>
        </BarChart></ResponsiveContainer></div> : <div className="reports-state"><h3>Sem aportes no período</h3><p>Não há compras ou aplicações registradas entre as datas selecionadas.</p></div>}
        <div className="table-scroll reports-table"><table><thead><tr><th>{bucket === 'month' ? 'Mês' : 'Ano'}</th><th>Ações · com taxas</th><th>Renda fixa · principal</th><th>Total aportado</th></tr></thead><tbody>{chartRows.map(row => <tr key={row.key}><td>{row.key}</td><td>{decimalMoney(row.equities)}</td><td>{decimalMoney(row.fixedIncome)}</td><td>{decimalMoney(row.total)}</td></tr>)}</tbody></table></div>
      </>}
    </article>
    <p className="reports-disclaimer">Relatório privado baseado nos movimentos efetivos desta carteira. Aportes não são lucro, rentabilidade, saldo em caixa nem avaliação a mercado. Datas usam os registros disponíveis; períodos sem lançamentos não aparecem.</p>
  </section>
}
