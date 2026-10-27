import type { Operation, Summary } from '../api'
import { initialOperations } from '../demo/fixtures'
import { summarizeDemo, validateOperation, type OperationInput } from '../demo/finance'

export const DEMO_STORAGE_KEY = 'investment-demo-portfolio'
const VERSION = 1
type Snapshot = { operations: readonly Operation[]; summary: Summary; notice: string }
type DemoStorage = Pick<Storage, 'getItem' | 'setItem'>

// Sem dependência de fetch, Supabase, JWT ou repositório privado.
export class DemoRepository {
  private storage: DemoStorage | null
  private state!: Snapshot
  private listeners = new Set<() => void>()
  constructor(storage?: DemoStorage | null) {
    try { this.storage = storage === undefined ? window.localStorage : storage } catch { this.storage = null }
    this.load()
  }
  private build(ops: readonly Operation[], notice = ''): Snapshot {
    const operations = ops.map(op => Object.freeze(validateOperation(op)))
    if (new Set(operations.map(op => op.id)).size !== operations.length) throw new Error('Identificadores duplicados.')
    return { operations: Object.freeze(operations), summary: summarizeDemo(operations), notice }
  }
  private load() {
    try {
      const raw = this.storage?.getItem(DEMO_STORAGE_KEY)
      if (!raw) { this.state = this.build(initialOperations, this.storage ? '' : 'Armazenamento indisponível. Suas alterações fictícias durarão apenas nesta sessão.'); return }
      const value = JSON.parse(raw)
      if (value.kind !== 'investment-demo' || value.version !== VERSION || !Array.isArray(value.operations) || value.operations.length > 10000) throw new Error('Formato incompatível.')
      this.state = this.build(value.operations)
    } catch {
      this.state = this.build(initialOperations, 'Os dados locais da demonstração estavam inválidos ou incompatíveis. A carteira fictícia inicial foi carregada; restaure para substituir o conteúdo local.')
    }
  }
  getSnapshot = () => this.state
  subscribe = (callback: () => void) => { this.listeners.add(callback); return () => { this.listeners.delete(callback) } }
  private commit(operations: readonly Operation[]) {
    if (operations.length > 10000) throw new Error('Limite de 10.000 operações demonstrativas atingido.')
    const next = this.build(operations)
    try {
      if (!this.storage) throw new Error('Storage indisponível')
      this.storage.setItem(DEMO_STORAGE_KEY, JSON.stringify({ kind: 'investment-demo', version: VERSION, operations: next.operations }))
    } catch { next.notice = 'Não foi possível salvar no navegador. As alterações fictícias estão disponíveis apenas nesta sessão.' }
    this.state = next
    this.listeners.forEach(callback => callback())
  }
  create(input: OperationInput) {
    const id = Math.max(0, ...this.state.operations.map(op => op.id)) + 1
    const op = validateOperation({ ...input, id })
    this.commit([...this.state.operations, op])
    return op
  }
  delete(id: number) {
    if (!this.state.operations.some(op => op.id === id)) throw new Error('Operação fictícia não encontrada.')
    // Recalcular antes de persistir: excluir compra não pode invalidar venda posterior.
    this.commit(this.state.operations.filter(op => op.id !== id))
  }
  reset() { this.commit(initialOperations) }
}
