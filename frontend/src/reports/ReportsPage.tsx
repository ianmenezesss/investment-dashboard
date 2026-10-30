import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Decimal from 'decimal.js'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download } from 'lucide-react'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { aggregateContributions, contributionRows, decimalMoney } from './contributions'
import { filterReportMovements, movementTotals, sharePercent } from './movementReport'
import './reports.css'

const today = () => new Date().toLocaleDateString('en-CA')
const thisYear = () => `${today().slice(0, 4)}-01-01`
const chartMoney = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value)

export function ReportsPage({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [start, setStart] = useState(thisYear)
  const [end, setEnd] = useState(today)
  const [bucket, setBucket] = useState<'month' | 'year'>('month')
  const [movementClass, setMovementClass] = useState('all')
  const [assetSearch, setAssetSearch] = useState('')
  const query = useQuery({ queryKey: ['reports-movements', identity], queryFn: ({ signal }) => repository.movements(signal), retry: false })
  const compositionQuery = useQuery({ queryKey: ['reports-composition', identity], queryFn: ({ signal }) => repository.composition(signal), retry: false })
  const reportMovements = useMemo(() => filterReportMovements(query.data ?? [], start, end, movementClass, assetSearch), [query.data, start, end, movementClass, assetSearch])
  const rows = useMemo(() => contributionRows(reportMovements, start, end), [reportMovements, start, end])
  const monthly = useMemo(() => aggregateContributions(rows, 'month'), [rows])
  const yearly = useMemo(() => aggregateContributions(rows, 'year'), [rows])
  const chartRows = bucket === 'month' ? monthly : yearly
  const equities = rows.filter(row => row.operation === 'BUY').reduce((sum, row) => sum.plus(row.financial_value ?? '0').plus(row.fees ?? '0'), new Decimal(0))
  const fixed = rows.filter(row => row.operation === 'APPLICATION').reduce((sum, row) => sum.plus(row.financial_value ?? '0'), new Decimal(0))
  const total = equities.plus(fixed)
  const generatedAt = new Date().toLocaleString('pt-BR')
  const totals = useMemo(() => movementTotals(reportMovements), [reportMovements])
  return <section className="reports-page" aria-label="Relatórios financeiros">
    <article className="panel reports-panel">
      <div className="panel-heading"><div><h2>Relatório de aportes</h2><p>Compras de ações incluem taxas; renda fixa considera principal aplicado. Valores registrados, sem rentabilidade ou valor de mercado.</p></div><button type="button" className="reports-print-button" onClick={() => window.print()}><Download size={15}/> Exportar PDF</button></div>
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
    <article className="panel reports-panel reports-holdings">
      <div className="panel-heading"><div><h2>Carteira por categoria e ativo</h2><p>Posições abertas por custo de aquisição em ações e principal efetivo em renda fixa. Valores declarados ficam separados; não é valor de mercado.</p></div></div>
      {compositionQuery.isPending ? <p role="status" className="reports-state">Carregando composição da carteira…</p> : compositionQuery.isError ? <p role="alert" className="reports-state">Não foi possível carregar a composição. Confira sua sessão e tente novamente.</p> : compositionQuery.data && <div className="reports-distributions">
        {([['Ações · custo aberto', compositionQuery.data.equities, compositionQuery.data.class_totals.equities_open_cost], ['Renda fixa · principal efetivo', compositionQuery.data.fixed_income, compositionQuery.data.class_totals.fixed_income_open_principal], ['Observações declaradas · separadas', compositionQuery.data.declared_positions, compositionQuery.data.class_totals.declared_positions]] as const).map(([title, items, totalValue]) => <section className="reports-distribution" key={title}><h3>{title}</h3><p>Total registrado: {decimalMoney(new Decimal(totalValue))}</p>{items.length ? <ul>{items.map((item, index) => <li key={`${item.asset}-${index}`}><span>{item.asset}<small>{item.basis === 'declared_observation' ? 'Observação declarada' : item.basis}</small></span><strong>{decimalMoney(new Decimal(item.value))}<small>{sharePercent(item.value, totalValue)}% da categoria</small></strong><i aria-hidden="true" style={{ width: `${Math.min(100, Number(sharePercent(item.value, totalValue)))}%` }}/></li>)}</ul> : <p>Sem posições disponíveis nesta categoria.</p>}</section>)}
      </div>}
    </article>
    <article className="panel reports-panel reports-movements">
      <div className="panel-heading"><div><h2>Compras, vendas e eventos financeiros</h2><p>Movimentações efetivas e eventos registrados no período; valores movimentados não representam lucro nem rendimento.</p></div></div>
      <div className="reports-movement-filters"><label>Categoria<select aria-label="Categoria das movimentações" value={movementClass} onChange={event => setMovementClass(event.target.value)}><option value="all">Todas</option><option>AÇÕES</option><option>CDB</option><option>FLUXO DE CAIXA</option><option>PROVENTOS</option><option>EVENTO SOCIETÁRIO</option></select></label><label>Ativo ou contrato<input aria-label="Buscar ativo no relatório" value={assetSearch} onChange={event => setAssetSearch(event.target.value)} placeholder="Buscar…"/></label></div>
      {query.isError ? <p role="alert" className="reports-state">Não foi possível carregar as movimentações.</p> : <>
        <div className="reports-summary reports-movement-totals"><div><span>Compras + aplicações</span><strong>{decimalMoney(totals.purchases)}</strong></div><div><span>Vendas líquidas + resgates</span><strong>{decimalMoney(totals.disposals)}</strong></div><div><span>Aportes + retiradas externos</span><strong>{decimalMoney(totals.external)}</strong></div><div><span>Proventos registrados</span><strong>{decimalMoney(totals.income)}</strong></div><div><span>Volume de compras/vendas</span><strong>{decimalMoney(totals.transactionVolume)}</strong></div><div><span>Registros no filtro</span><strong>{totals.count}</strong></div></div>
        {reportMovements.length ? <div className="table-scroll reports-table"><table><thead><tr><th>Data</th><th>Categoria</th><th>Ativo/contrato</th><th>Operação</th><th>Valor</th><th>Taxas</th><th>Caixa recebido</th><th>Bruto / tributos</th><th>Origem / descrição</th></tr></thead><tbody>{reportMovements.map(row => <tr key={`${row.id}:${row.revision ?? 0}`}><td>{new Date(`${row.date}T12:00:00`).toLocaleDateString('pt-BR')}</td><td>{row.investment_class}</td><td>{row.asset}</td><td>{row.operation}{row.revision ? ` · rev. ${row.revision}` : ''}</td><td>{row.financial_value === null ? '—' : decimalMoney(new Decimal(row.financial_value))}</td><td>{row.fees === null ? '—' : decimalMoney(new Decimal(row.fees))}</td><td>{row.cash_received === null ? '—' : decimalMoney(new Decimal(row.cash_received))}</td><td>{row.gross_amount == null ? '—' : `${decimalMoney(new Decimal(row.gross_amount))}${row.tax_withheld == null ? '' : ` · tributos ${decimalMoney(new Decimal(row.tax_withheld))}`}`}</td><td>{[row.source, row.description].filter(Boolean).join(' · ') || '—'}</td></tr>)}</tbody></table></div> : <div className="reports-state"><h3>Nenhuma movimentação no filtro</h3><p>Altere as datas, categoria ou ativo.</p></div>}
      </>}
    </article>
    <p className="reports-print-meta">Período: {start || 'início não definido'} a {end || 'fim não definido'} · Agrupamento: {bucket === 'month' ? 'mês' : 'ano'} · Categoria: {movementClass === 'all' ? 'todas' : movementClass} · Ativo: {assetSearch.trim() || 'todos'} · Gerado em {generatedAt}</p>
    <p className="reports-disclaimer">Relatório privado baseado nos movimentos efetivos desta carteira. Aportes não são lucro, rentabilidade, saldo em caixa nem avaliação a mercado. Datas usam os registros disponíveis; períodos sem lançamentos não aparecem.</p>
  </section>
}
