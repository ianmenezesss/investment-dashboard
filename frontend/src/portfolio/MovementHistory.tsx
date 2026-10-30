import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { PrivateRepository, UnifiedMovement } from '../repositories/PrivateRepository'
import { marketMoney, marketQuantity } from '../components/market-format'
import { FinancialEventEntry } from './FinancialEventEntry'
import { FinancialEventCorrection } from './FinancialEventCorrection'
import './portfolio.css'

const money = (value: string | null) => value === null ? '—' : marketMoney(value)
const quantity = (value: string | null) => value === null ? '—' : marketQuantity(value)
const labels: Record<UnifiedMovement['operation'], string> = {
  BUY: 'Compra', SELL: 'Venda', APPLICATION: 'Aplicação', REDEMPTION: 'Resgate',
  CONTRIBUTION: 'Aporte externo', WITHDRAWAL: 'Retirada externa', DIVIDEND: 'Dividendo',
  JCP: 'JCP', CORPORATE_ACTION: 'Observação societária',
}
const classLabels: Record<UnifiedMovement['investment_class'], string> = {
  'AÇÕES': 'Ações', CDB: 'CDB', 'FLUXO DE CAIXA': 'Fluxo de caixa',
  PROVENTOS: 'Proventos', 'EVENTO SOCIETÁRIO': 'Evento societário',
}

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
      <label>Classe<select aria-label="Filtrar por classe" value={investmentClass} onChange={event => setInvestmentClass(event.target.value)}><option>Todas</option>{Object.entries(classLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Ativo ou contrato<input aria-label="Filtrar por ativo" placeholder="Buscar…" value={asset} onChange={event => setAsset(event.target.value)}/></label>
    </div>
    {query.isPending ? <p role="status" className="unified-history-state">Carregando movimentações…</p> : query.isError ? <div className="unified-history-state" role="alert">Não foi possível carregar o histórico. <button onClick={() => { void query.refetch() }}>Tentar novamente</button></div> : rows.length === 0 ? <div className="empty compact"><h4>Nenhuma movimentação encontrada</h4><p>Revise os filtros ou registre uma operação na carteira.</p></div> : <div className="table-scroll unified-history-table" role="region" aria-label="Movimentações ordenadas por data, mais recentes primeiro" tabIndex={0}><table><thead><tr>{['Data', 'Classe', 'Ativo ou contrato', 'Operação', 'Quantidade', 'Preço unitário', 'Valor financeiro', 'Taxas', 'Caixa recebido', 'Origem e observações', 'Revisões'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row => {
      const eventId = row.id.startsWith('event:') ? Number(row.id.slice('event:'.length)) : null
      const validEventId = Number.isSafeInteger(eventId) && (eventId ?? 0) > 0 ? eventId : null
      return <tr key={`${row.id}:${row.revision ?? 0}`}><td>{new Date(`${row.date}T12:00:00`).toLocaleDateString('pt-BR')}</td><td>{classLabels[row.investment_class]}</td><td>{row.asset}</td><td>{labels[row.operation]}{row.revision ? ` · rev. ${row.revision}` : ''}</td><td>{quantity(row.quantity)}</td><td>{money(row.unit_price)}</td><td>{money(row.financial_value)}</td><td>{money(row.fees)}</td><td>{money(row.cash_received)}</td><td>{[row.source, row.description, row.gross_amount !== undefined && row.gross_amount !== null ? `Bruto ${money(row.gross_amount)}` : null, row.tax_withheld !== undefined && row.tax_withheld !== null ? `Imposto ${money(row.tax_withheld)}` : null].filter(Boolean).join(' · ') || '—'}</td><td>{validEventId !== null && <FinancialEventCorrection key={validEventId} repository={repository} identity={identity} row={row} eventId={validEventId}/>}</td></tr>
    })}</tbody></table></div>}
    {!query.isPending && !query.isError && <div className="table-footer">{rows.length} movimentações encontradas</div>}
    <FinancialEventEntry repository={repository}/>
  </article>
}
