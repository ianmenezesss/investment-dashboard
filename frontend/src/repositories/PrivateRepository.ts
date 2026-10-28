import { request, type Operation, type PortfolioValuation } from '../api'
import type { OperationInput } from '../demo/finance'
import type { Cdb, CdbInput, CdbDetail, CdbMovement, ApplicationInput, RedemptionInput, ReturnsInput, CdbReturns, CdbApplicationRevision, CdbApplicationRevisionInput, CdbApplicationRevisionPreview } from '../fixed-income/types'
import type { ObservedPosition, ObservedPositionInput } from '../fixed-income/types'

// Nunca recebe Storage ou dados da demonstração.
export class PrivateRepository {
  constructor(private token: string) {}
  list(signal?: AbortSignal) { return request<Operation[]>('operations', this.token, { signal }) }
  summary(signal?: AbortSignal) { return request<PortfolioValuation>('dashboard/valuation', this.token, { signal }) }
  create(input: OperationInput) { return request<Operation>('operations', this.token, { method: 'POST', body: JSON.stringify(input) }) }
  delete(id: number) { return request<void>(`operations/${id}`, this.token, { method: 'DELETE' }) }
  export() { return request('export', this.token) }
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
