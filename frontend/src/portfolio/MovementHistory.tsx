import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { PrivateRepository, UnifiedMovement } from '../repositories/PrivateRepository'
import './portfolio.css'

const money = (value: string | null) => value === null ? '—' : Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const quantity = (value: string | null) => value === null ? '—' : Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 8 })
const labels: Record<UnifiedMovement['operation'], string> = { BUY: 'Compra', SELL: 'Venda', APPLICATION: 'Aplicação', REDEMPTION: 'Resgate' }

export function MovementHistory({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [investmentClass, setInvestmentClass] = useState('Todas')
  const [asset, setAsset] = useState('')
  const query = useQuery({ queryKey: ['unified-movements', identity], queryFn: async ({ signal }) => {
    const response = await repository.movements(signal)
    if (!Array.isArray(response)) throw new Error('Resposta inválida do histórico de movimentações.')
    return response
  }, retry: false })
  const rows = useMemo(() => (query.data ?? []).filter(row =>
    (!start || row.date >= start) && (!end || row.date <= end) &&
    (investmentClass === 'Todas' || row.investment_class === investmentClass) &&
    row.asset.toLocaleLowerCase('pt-BR').includes(asset.trim().toLocaleLowerCase('pt-BR'))
  ).sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id)), [query.data, start, end, investmentClass, asset])

  return <article className="panel unified-history" aria-label="Histórico cronológico de movimentações">
    <div className="panel-heading"><div><h3>Histórico de movimentações</h3><p>Ações e CDBs · valores efetivamente registrados</p></div></div>
    <div className="unified-history-filters">
      <label>De<input type="date" aria-label="Data inicial" value={start} onChange={event => setStart(event.target.value)}/></label>
      <label>Até<input type="date" aria-label="Data final" value={end} onChange={event => setEnd(event.target.value)}/></label>
      <label>Classe<select aria-label="Filtrar por classe" value={investmentClass} onChange={event => setInvestmentClass(event.target.value)}><option>Todas</option><option value="AÇÕES">Ações</option><option value="CDB">CDB</option></select></label>
      <label>Ativo ou contrato<input aria-label="Filtrar por ativo" placeholder="Buscar…" value={asset} onChange={event => setAsset(event.target.value)}/></label>
    </div>
    {query.isPending ? <p role="status" className="unified-history-state">Carregando movimentações…</p> : query.isError ? <div className="unified-history-state" role="alert">Não foi possível carregar o histórico. <button onClick={() => { void query.refetch() }}>Tentar novamente</button></div> : rows.length === 0 ? <div className="empty compact"><h4>Nenhuma movimentação encontrada</h4><p>Revise os filtros ou registre uma operação na carteira.</p></div> : <div className="table-scroll unified-history-table" role="region" aria-label="Movimentações ordenadas por data, mais recentes primeiro" tabIndex={0}><table><thead><tr>{['Data', 'Classe', 'Ativo ou contrato', 'Operação', 'Quantidade', 'Preço unitário', 'Valor financeiro', 'Taxas', 'Caixa recebido'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{new Date(`${row.date}T12:00:00`).toLocaleDateString('pt-BR')}</td><td>{row.investment_class === 'AÇÕES' ? 'Ações' : 'CDB'}</td><td>{row.asset}</td><td>{labels[row.operation]}</td><td>{quantity(row.quantity)}</td><td>{money(row.unit_price)}</td><td>{money(row.financial_value)}</td><td>{money(row.fees)}</td><td>{money(row.cash_received)}</td></tr>)}</tbody></table></div>}
    {!query.isPending && !query.isError && <div className="table-footer">{rows.length} movimentações encontradas</div>}
  </article>
}
