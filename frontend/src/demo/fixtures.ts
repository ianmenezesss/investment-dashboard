import type { Operation } from '../api'

// Preços e operações inventados; não representam cotações reais.
export const initialOperations: readonly Operation[] = [
  { id: 1, ticker: 'ITUB4', kind: 'BUY', date: '2026-01-15', quantity: '100', price: '32.50', fees: '0' },
  { id: 2, ticker: 'BBAS3', kind: 'BUY', date: '2026-03-10', quantity: '200', price: '25.20', fees: '0' },
  { id: 3, ticker: 'B3SA3', kind: 'BUY', date: '2026-05-06', quantity: '300', price: '12.40', fees: '0' },
  { id: 4, ticker: 'ITUB4', kind: 'BUY', date: '2026-07-20', quantity: '150', price: '34.00', fees: '0' },
]
