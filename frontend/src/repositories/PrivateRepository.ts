import { request, type CapitalFlows, type FinancialPerformance, type Operation, type PortfolioComposition, type PortfolioValuation } from '../api'
import type { OperationInput } from '../demo/finance'
import type { Cdb, CdbInput, CdbDetail, CdbMovement, ApplicationInput, RedemptionInput, ReturnsInput, CdbReturns, CdbApplicationRevision, CdbApplicationRevisionInput, CdbApplicationRevisionPreview } from '../fixed-income/types'
import type { ObservedPosition, ObservedPositionInput } from '../fixed-income/types'

export type FinancialEventKind = 'CONTRIBUTION' | 'WITHDRAWAL' | 'DIVIDEND' | 'JCP' | 'CORPORATE_ACTION'
export type FinancialEventInput = { kind: FinancialEventKind; event_date: string; ticker?: string | null; cash_amount?: string | null; gross_amount?: string | null; tax_withheld?: string | null; source: string; description?: string | null }
export type FinancialEventRecord = FinancialEventInput & { id: number; ticker: string | null; cash_amount: string | null; gross_amount: string | null; tax_withheld: string | null; description: string | null; revision: number }
export type FinancialEventRevision = { id: number; event_id: number; revision: number; kind: 'REPLACE' | 'VOID'; reason: string; replacement_kind: FinancialEventKind | null; replacement_date: string | null; replacement_ticker: string | null; replacement_cash_amount: string | null; replacement_gross_amount: string | null; replacement_tax_withheld: string | null; replacement_source: string | null; replacement_description: string | null; created_at: string }
export type FinancialEventSummary = { period_start: string | null; period_end: string; coverage: 'available' | 'empty'; contributions: string; withdrawals: string; net_external_cash_flow: string; dividends_received: string; jcp_received: string; income_total_received: string; event_count: number }
export type UnifiedMovement = { id: string; date: string; investment_class: 'AÇÕES' | 'CDB' | 'FLUXO DE CAIXA' | 'PROVENTOS' | 'EVENTO SOCIETÁRIO'; asset: string; operation: 'BUY' | 'SELL' | 'APPLICATION' | 'REDEMPTION' | FinancialEventKind; quantity: string | null; unit_price: string | null; financial_value: string | null; fees: string | null; cash_received: string | null; gross_amount?: string | null; tax_withheld?: string | null; source?: string | null; description?: string | null; revision?: number }

// Nunca recebe Storage ou dados da demonstração.
export class PrivateRepository {
  constructor(private token: string) {}
  list(signal?: AbortSignal) { return request<Operation[]>('operations', this.token, { signal }) }
  summary(signal?: AbortSignal) { return request<PortfolioValuation>('dashboard/valuation', this.token, { signal }) }
  performance(signal?: AbortSignal) { return request<FinancialPerformance>('dashboard/performance', this.token, { signal }) }
  capitalFlows(period: string, signal?: AbortSignal) { return request<CapitalFlows>(`dashboard/capital-flows?period=${period}`, this.token, { signal }) }
  composition(signal?: AbortSignal) { return request<PortfolioComposition>('dashboard/composition', this.token, { signal }) }
  movements(signal?: AbortSignal) { return request<UnifiedMovement[]>('dashboard/movements', this.token, { signal }) }
  financialEvents(signal?: AbortSignal) { return request<FinancialEventRecord[]>('financial-events', this.token, { signal }) }
  financialEventSummary(period = 'Tudo', signal?: AbortSignal) { return request<FinancialEventSummary>(`dashboard/financial-events/summary?period=${period}`, this.token, { signal }) }
  createFinancialEvent(input: FinancialEventInput, key: string, signal?: AbortSignal) {
    return request<FinancialEventRecord>('financial-events', this.token, { method: 'POST', body: JSON.stringify(input), signal, headers: { 'Idempotency-Key': key } })
  }
  importFinancialEvents(rows: Array<{ row_number: number; event: FinancialEventInput }>, key: string, signal?: AbortSignal) {
    return request<{ imported_count: number; duplicate_count: number }>('financial-events/import', this.token, {
      method: 'POST', body: JSON.stringify({ rows }), signal, headers: { 'Idempotency-Key': key },
    })
  }
  reviseFinancialEvent(id: number, input: { kind: 'REPLACE' | 'VOID'; expected_revision: number; reason: string; replacement?: FinancialEventInput }, key: string, signal?: AbortSignal) {
    return request(`financial-events/${id}/revisions`, this.token, { method: 'POST', body: JSON.stringify(input), signal, headers: { 'Idempotency-Key': key } })
  }
  financialEventRevisions(id: number, signal?: AbortSignal) { return request<FinancialEventRevision[]>(`financial-events/${id}/revisions`, this.token, { signal }) }
  equityHistory(period: string, signal?: AbortSignal) { return request<import('../api').EquityHistory>(`dashboard/equity-history?period=${period}`, this.token, { signal }) }
  equityPriceHistory(ticker: string, period: import('../api').IndividualEquityPriceHistory['period'], signal?: AbortSignal) {
    return request<import('../api').IndividualEquityPriceHistory>(`dashboard/equities/${encodeURIComponent(ticker)}/price-history?period=${period}`, this.token, { signal })
  }
  equityComparison(tickers: string[], period: import('../api').IndividualEquityPriceHistory['period'], signal?: AbortSignal) {
    const params = new URLSearchParams()
    tickers.forEach(ticker => params.append('tickers', ticker))
    params.set('period', period)
    return request<import('../api').EquityComparison>(`dashboard/equities/compare?${params.toString()}`, this.token, { signal })
  }
  create(input: OperationInput) { return request<Operation>('operations', this.token, { method: 'POST', body: JSON.stringify(input) }) }
  delete(id: number) { return request<void>(`operations/${id}`, this.token, { method: 'DELETE' }) }
  export() { return request('export', this.token) }
  observedHistory(id: number, start: string, end: string, signal: AbortSignal) { return request<import("../fixed-income/ObservedHistory").ObservedSeries>(`fixed-income/investments/${id}/observed-history?start=${start}&end=${end}`, this.token, { signal }) }
  cdbs(offset = 0, signal?: AbortSignal) { return request<Cdb[]>(`fixed-income/investments?offset=${offset}&limit=20`, this.token, { signal }) }
  cdb(id: number, signal?: AbortSignal) { return request<CdbDetail>(`fixed-income/investments/${id}`, this.token, { signal }) }
  cdbMovements(id: number, offset = 0, signal?: AbortSignal) { return request<CdbMovement[]>(`fixed-income/investments/${id}/effective-movements?offset=${offset}&limit=100`, this.token, { signal }) }
  cdbOriginalMovements(id: number, offset = 0, signal?: AbortSignal) { return request<CdbMovement[]>(`fixed-income/investments/${id}/movements?offset=${offset}&limit=100`, this.token, { signal }) }
  createCdb(input: CdbInput, signal?: AbortSignal) { return request<Cdb>('fixed-income/investments', this.token, { method: 'POST', body: JSON.stringify(input), signal }) }
  applyCdb(id: number, input: ApplicationInput, signal?: AbortSignal) { return request<CdbMovement>(`fixed-income/investments/${id}/applications`, this.token, { method: 'POST', body: JSON.stringify(input), signal }) }
  redeemCdb(id: number, input: RedemptionInput, signal?: AbortSignal) { return request<CdbMovement>(`fixed-income/investments/${id}/redemptions`, this.token, { method: 'POST', body: JSON.stringify(input), signal }) }
  cdbReturns(id: number, input: ReturnsInput, signal?: AbortSignal) { return request<CdbReturns>(`fixed-income/investments/${id}/returns?${new URLSearchParams(input)}`, this.token, { signal }) }
  cdbObservations(id: number, offset = 0, signal?: AbortSignal) { return request<ObservedPosition[]>(`fixed-income/investments/${id}/observations?offset=${offset}&limit=100`, this.token, { signal }) }
  saveCdbObservation(id: number, input: ObservedPositionInput, opening: boolean, signal?: AbortSignal) { return request<ObservedPosition>(`fixed-income/investments/${id}/${opening ? 'opening-balance' : 'observations'}`, this.token, { method: 'POST', body: JSON.stringify(input), signal }) }
  archiveCdb(id: number, signal?: AbortSignal) { return request<void>(`fixed-income/investments/${id}/archive`, this.token, { method: 'DELETE', signal }) }
  cdbApplicationRevisions(id: number, movementId: number, offset = 0, signal?: AbortSignal) {
    return request<CdbApplicationRevision[]>(`fixed-income/investments/${id}/applications/${movementId}/revisions?offset=${offset}&limit=100`, this.token, { signal })
  }
  async latestCdbApplicationRevision(id: number, movementId: number, signal?: AbortSignal) {
    let offset = 0, latest = 0
    while (true) {
      const page = await this.cdbApplicationRevisions(id, movementId, offset, signal)
      if (page.length) latest = page[page.length - 1].revision
      if (page.length < 100) return latest
      offset += page.length
    }
  }
  previewCdbApplicationRevision(id: number, movementId: number, input: CdbApplicationRevisionInput, key: string, signal?: AbortSignal) {
    return request<CdbApplicationRevisionPreview>(`fixed-income/investments/${id}/applications/${movementId}/revisions/preview`, this.token, {
      method: 'POST', body: JSON.stringify(input), signal, headers: { 'Idempotency-Key': key },
    })
  }
  createCdbApplicationRevision(id: number, movementId: number, input: CdbApplicationRevisionInput, key: string, signal?: AbortSignal) {
    return request<CdbApplicationRevision>(`fixed-income/investments/${id}/applications/${movementId}/revisions`, this.token, {
      method: 'POST', body: JSON.stringify(input), signal, headers: { 'Idempotency-Key': key },
    })
  }
}
