import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { Button } from '../components/ui/button'
import { marketMoney } from '../components/market-format'
import { dayLabel, financialToday, timeLabel } from './format'
import type { CdbDetail, CdbLotReturns, ReturnsInput } from './types'

const states: Record<CdbLotReturns['status'], string> = {
  estimated: 'Estimativa disponível', closed: 'Lote encerrado · sem posição aberta', convention_required: 'Convenção não confirmada', calendar_required: 'Calendário não confirmado',
  unsupported_calendar: 'Calendário fora da cobertura 2024–2026', unsupported_product: 'Produto não suportado pelo motor CDI', incomplete_history: 'Histórico CDI incompleto',
  invalid_rates: 'Taxas incompatíveis com as premissas', rates_unavailable: 'Fornecedor de taxas indisponível', tax_profile_required: 'Perfil tributário não confirmado', matured_unsettled: 'Vencido com principal sem liquidação registrada',
}
export function FixedIncomeReturns({ detail, repository, identity, onAuthError }: {
  detail: CdbDetail; repository: PrivateRepository; identity: string; onAuthError: (error: ApiError) => void
}) {
  const [input, setInput] = useState<ReturnsInput | null>(null)
  const query = useQuery({ queryKey: ['fixed-income', identity, 'returns', detail.id, input],
    queryFn: ({ signal }) => repository.cdbReturns(detail.id, input!, signal), enabled: input !== null,
    retry: false, staleTime: 15 * 60 * 1000, refetchOnWindowFocus: false, refetchInterval: false })
  useEffect(() => { if (query.error instanceof ApiError && [401, 403].includes(query.error.status)) onAuthError(query.error) }, [query.error, onAuthError])
  const data = query.isError ? undefined : query.data
  if (detail.remuneration !== 'CDI') return <article className="panel fi-section"><h3>Rentabilidade</h3><p>O contrato prefixado pode receber aplicações e resgates. O motor atual estima somente CDBs percentuais do CDI; não há cálculo prefixado disponível.</p></article>
  return <article className="panel fi-section" aria-label="Estimativa de rentabilidade">
    <h3>Rentabilidade estimada</h3><p>Consulta pontual da posição aberta, sem garantia de liquidação. Confirme que as premissas correspondem ao seu contrato.</p>
    <form className="fi-premises" onChange={() => setInput(null)} onSubmit={event => {
      event.preventDefault()
      const form = new FormData(event.currentTarget)
      if (['convention', 'calendar', 'tax_profile'].some(name => form.get(name) !== 'on')) return
      setInput({ as_of: String(form.get('as_of')), convention: 'daily_cdi_pro_rata_decimal_v1', calendar: 'anbima_2024_2026_v1', tax_profile: 'br_resident_individual' })
    }}>
      <label>Data de avaliação<input type="date" name="as_of" required min={detail.application_date} max={financialToday()} defaultValue={financialToday()}/></label>
      <fieldset><legend>Premissas obrigatórias</legend>
        <label><input type="checkbox" name="convention" required/> Percentual diário do CDI, amortização proporcional, sem spread, cupons ou custos intermediários.</label>
        <label><input type="checkbox" name="calendar" required/> Meu contrato é compatível com o calendário nacional ANBIMA 2024–2026.</label>
        <label><input type="checkbox" name="tax_profile" required/> Pessoa física residente no Brasil, CDB tributável comum, sem regime especial.</label>
      </fieldset>
      <Button type="submit" disabled={query.isFetching}>{query.isFetching ? 'Consultando…' : 'Consultar estimativa'}</Button>
    </form>
    <p className="fi-notice">Não é cálculo definitivo de liquidação nem réplica exata dos arredondamentos do emissor. Datas sem CDI publicado não recebem taxas inventadas.</p>
    {query.isFetching && <p role="status">Consultando posição e histórico CDI…</p>}
    {query.isError && <div role="alert" className="error">{(query.error as Error).message} {query.error instanceof ApiError && query.error.status === 404 && 'Confirme se o backend publicado inclui a Fase 2.0.3.'}<Button variant="outline" onClick={() => { void query.refetch() }}>Tentar novamente</Button></div>}
    {!input && <p>Confirme as premissas para consultar. Nenhuma cotação externa é solicitada automaticamente por esta seção.</p>}
    {data && input && <>
      <div className="fi-notice" role="status"><strong>{data.status === 'incomplete' ? 'Estimativa incompleta · valores indisponíveis preservados' : data.status === 'empty' ? 'Sem posição na data consultada' : 'Estimativa da posição aberta'}</strong>
        <p>Data-base: {dayLabel(data.as_of)} · Ledger capturado em {timeLabel(data.ledger_as_of)} · Modelo {data.model_version}</p>
        {data.rates_error && <p>Não foi possível obter todo o histórico CDI. O principal continua conhecido; rendimento não é confirmado.</p>}
      </div>
      <div className="fi-metrics">{([
        ['Principal na data consultada', data.principal_balance], ['Rendimento bruto estimado', data.gross_income_estimate],
        ['IOF estimado', data.iof_estimate], ['IR estimado', data.ir_estimate], ['Rendimento líquido estimado', data.net_income_estimate], ['Valor líquido estimado', data.net_value_estimate],
      ] as const).map(([label, value]) => <article className="metric" key={label}><span>{label}</span><h2>{marketMoney(value)}</h2></article>)}</div>
      <p>Valor bruto estimado: <strong>{marketMoney(data.gross_value_estimate)}</strong>. Taxas e tributos são estimativas sobre a posição aberta, não valores efetivamente retidos.</p>
      <div className="table-scroll" role="region" aria-label="Estimativa por lote" tabIndex={0}><table><caption className="sr-only">Rentabilidade estimada por lote</caption><thead><tr>{['Lote', 'Situação', 'Rendimento bruto', 'IOF', 'IR', 'Líquido estimado', 'Referência'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{data.lots.map(lot => <tr key={lot.lot_id}><th scope="row">{lot.lot_id}</th><td>{states[lot.status]}{lot.missing_rate_dates.length > 0 && <details><summary>{lot.missing_rate_dates.length} datas sem CDI</summary>{lot.missing_rate_dates.map(day => <div key={day}>{dayLabel(day)}</div>)}</details>}</td>
          <td>{marketMoney(lot.gross_income_estimate)}</td><td>{marketMoney(lot.iof_estimate)}</td><td>{marketMoney(lot.ir_estimate)}</td><td>{marketMoney(lot.net_value_estimate)}</td>
          <td>Aplicação: {dayLabel(lot.application_date)}<small>Capitalização até {dayLabel(lot.accrual_end_exclusive)} (exclusive)</small><small>Base fiscal: {dayLabel(lot.tax_basis_date)} · {lot.calendar_days} dias corridos</small></td></tr>)}</tbody></table></div>
      <p className="fi-notice">{data.lots.some(lot => lot.realized_tax_status === 'insufficient_information') ? 'Resultados realizados, IR e IOF de resgates: informação insuficiente. O caixa recebido não permite separar esses componentes.' : 'Não há resgate realizado nesse snapshot. A estimativa não registra impostos no ledger.'}</p>
      {data.rates_references.map((reference, index) => <p className="fi-reference" key={index}>CDI · BCB/SGS 12 · {dayLabel(reference.start_date)} a {dayLabel(reference.end_date)} · Coletado em {timeLabel(reference.fetched_at)} · Expira em {timeLabel(reference.expires_at)}{reference.from_cache ? ' · Cache do backend' : ''}</p>)}
      <p>Não há série histórica de patrimônio nesta consulta. Gráficos de evolução dependem de dados reais suficientes e estão planejados para a Fase 3.</p>
    </>}
  </article>
}
