import { request, type Operation, type Summary } from '../api'
import type { OperationInput } from '../demo/finance'

// Nunca recebe Storage ou dados da demonstração.
export class PrivateRepository {
  constructor(private token: string) {}
  list(signal?: AbortSignal) { return request<Operation[]>('operations', this.token, { signal }) }
  summary(signal?: AbortSignal) { return request<Summary>('dashboard', this.token, { signal }) }
  create(input: OperationInput) { return request<Operation>('operations', this.token, { method: 'POST', body: JSON.stringify(input) }) }
  delete(id: number) { return request<void>(`operations/${id}`, this.token, { method: 'DELETE' }) }
  export() { return request('export', this.token) }
}
