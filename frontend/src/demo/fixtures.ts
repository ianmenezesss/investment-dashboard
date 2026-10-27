import type { Operation } from '../api'

// Preços e operações inventados; não representam cotações reais.
export const DEMO_SEED_VERSION = 2
export const initialOperations: readonly Operation[] = [
  { id: 1, ticker: 'ITUB4', kind: 'BUY', date: '2026-01-08', quantity: '100', price: '32.50', fees: '2.50' },
  { id: 2, ticker: 'BBAS3', kind: 'BUY', date: '2026-01-12', quantity: '200', price: '25.20', fees: '3' },
  { id: 3, ticker: 'B3SA3', kind: 'BUY', date: '2026-01-20', quantity: '300', price: '12.40', fees: '2' },
  { id: 4, ticker: 'PETR4', kind: 'BUY', date: '2026-02-03', quantity: '100', price: '37.20', fees: '3' },
  { id: 5, ticker: 'WEGE3', kind: 'BUY', date: '2026-02-12', quantity: '50', price: '45.80', fees: '2' },
  { id: 6, ticker: 'SBSP3', kind: 'BUY', date: '2026-02-23', quantity: '30', price: '68.40', fees: '1.50' },
  { id: 7, ticker: 'ITUB4', kind: 'BUY', date: '2026-03-05', quantity: '50', price: '33.80', fees: '1.50' },
  { id: 8, ticker: 'BBAS3', kind: 'BUY', date: '2026-03-10', quantity: '100', price: '24.60', fees: '2' },
  { id: 9, ticker: 'B3SA3', kind: 'BUY', date: '2026-03-18', quantity: '100', price: '11.90', fees: '1' },
  { id: 10, ticker: 'PETR4', kind: 'BUY', date: '2026-04-02', quantity: '50', price: '38.40', fees: '1.50' },
  { id: 11, ticker: 'WEGE3', kind: 'BUY', date: '2026-04-14', quantity: '25', price: '43.20', fees: '1' },
  { id: 12, ticker: 'SBSP3', kind: 'BUY', date: '2026-04-23', quantity: '20', price: '71.50', fees: '1.50' },
  { id: 13, ticker: 'ITUB4', kind: 'SELL', date: '2026-05-06', quantity: '40', price: '38.10', fees: '2' },
  { id: 14, ticker: 'BBAS3', kind: 'SELL', date: '2026-05-19', quantity: '50', price: '22.80', fees: '2' },
  { id: 15, ticker: 'B3SA3', kind: 'BUY', date: '2026-06-03', quantity: '200', price: '12.80', fees: '2' },
  { id: 16, ticker: 'PETR4', kind: 'SELL', date: '2026-06-16', quantity: '40', price: '35.40', fees: '2' },
  { id: 17, ticker: 'WEGE3', kind: 'BUY', date: '2026-06-25', quantity: '30', price: '46.70', fees: '1.50' },
  { id: 18, ticker: 'ITUB4', kind: 'BUY', date: '2026-07-07', quantity: '100', price: '34.90', fees: '2.50' },
  { id: 19, ticker: 'SBSP3', kind: 'SELL', date: '2026-07-21', quantity: '10', price: '78.30', fees: '1' },
  { id: 20, ticker: 'BBAS3', kind: 'BUY', date: '2026-08-04', quantity: '150', price: '24.10', fees: '2' },
  { id: 21, ticker: 'B3SA3', kind: 'SELL', date: '2026-08-18', quantity: '100', price: '14.20', fees: '1.50' },
  { id: 22, ticker: 'PETR4', kind: 'BUY', date: '2026-09-02', quantity: '80', price: '36.90', fees: '2' },
  { id: 23, ticker: 'WEGE3', kind: 'SELL', date: '2026-09-15', quantity: '20', price: '49.50', fees: '1' },
  { id: 24, ticker: 'SBSP3', kind: 'BUY', date: '2026-09-24', quantity: '15', price: '69.90', fees: '1' },
  { id: 25, ticker: 'ITUB4', kind: 'BUY', date: '2026-10-07', quantity: '50', price: '36.20', fees: '1.50' },
  { id: 26, ticker: 'BBAS3', kind: 'BUY', date: '2026-10-20', quantity: '100', price: '25.40', fees: '2' },
]
