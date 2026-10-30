import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { GenericCsvImport, parseGenericCsv } from './GenericCsvImport'
import type { FinancialEventInput } from '../repositories/PrivateRepository'

let host: HTMLDivElement, root: Root
beforeEach(() => { host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks() })

test('parses quoted semicolon CSV, escaped quotes, and embedded line breaks', () => {
  expect(parseGenericCsv('Data;Tipo;Valor;Ticker\r\n"01/02/2025";DIVIDEND;"1.234,50";"ITUB4"\r\n"02/02/2025";JCP;2,00;"ITUB4"')).toEqual([
    ['Data', 'Tipo', 'Valor', 'Ticker'], ['01/02/2025', 'DIVIDEND', '1.234,50', 'ITUB4'], ['02/02/2025', 'JCP', '2,00', 'ITUB4'],
  ])
  expect(parseGenericCsv('a,b\n"texto, com ""aspas""\ne quebra",2')).toEqual([['a', 'b'], ['texto, com "aspas"\ne quebra', '2']])
  expect(() => parseGenericCsv('a,b\n1')).toThrow('quantidade irregular')
  expect(() => parseGenericCsv('a,b\n"sem fechamento,2')).toThrow('aspas sem fechamento')
})

test('preview and cancel make no write; confirmation sends only valid rows in one batch', async () => {
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111')
  const repository = {
    financialEvents: vi.fn(async () => []),
    importFinancialEvents: vi.fn(async (_rows: Array<{ row_number: number; event: FinancialEventInput }>, _key: string) => ({ imported_count: 1, duplicate_count: 0 })),
  }
  await act(async () => root.render(<GenericCsvImport repository={repository}/>))
  const csv = 'date;kind;amount;ticker\n2025-01-02;CONTRIBUTION;100;\ninvalid;DIVIDEND;bad;ITUB4\n2025-01-02;CONTRIBUTION;100;'
  const file = new File([csv], 'fixture.csv', { type: 'text/csv' })
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode(csv).buffer as ArrayBuffer })
  const input = host.querySelector('[aria-label="Selecionar arquivo CSV"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); await new Promise(resolve => setTimeout(resolve, 0)) })
  expect(repository.financialEvents).toHaveBeenCalledOnce()
  expect(repository.importFinancialEvents).not.toHaveBeenCalled()
  const source = host.querySelector('[aria-label="Origem do registro"]') as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(source, 'Extrato fictício')
    source.dispatchEvent(new Event('input', { bubbles: true })); source.dispatchEvent(new Event('change', { bubbles: true }))
  })
  for (const [field, index] of [['event_date', 0], ['kind', 1], ['cash_amount', 2], ['ticker', 3]] as const) {
    const select = host.querySelector(`[aria-label="Mapear ${field}"]`) as HTMLSelectElement
    select.value = String(index)
    await act(async () => select.dispatchEvent(new Event('change', { bubbles: true })))
  }
  expect(host.textContent).toContain('1 válidas, 1 inválidas, 1 possíveis duplicatas')
  const cancel = [...host.querySelectorAll('button')].find(button => button.textContent === 'Cancelar')!
  await act(async () => cancel.click())
  expect(repository.importFinancialEvents).not.toHaveBeenCalled()

  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); await new Promise(resolve => setTimeout(resolve, 0)) })
  for (const [field, index] of [['event_date', 0], ['kind', 1], ['cash_amount', 2], ['ticker', 3]] as const) {
    const select = host.querySelector(`[aria-label="Mapear ${field}"]`) as HTMLSelectElement
    select.value = String(index)
    await act(async () => select.dispatchEvent(new Event('change', { bubbles: true })))
  }
  const checkbox = host.querySelector('input[type="checkbox"]') as HTMLInputElement
  await act(async () => checkbox.click())
  const importButton = [...host.querySelectorAll('button')].find(button => button.textContent === 'Importar lote confirmado')!
  await act(async () => { importButton.click(); await new Promise(resolve => setTimeout(resolve, 0)) })
  expect(repository.importFinancialEvents).toHaveBeenCalledOnce()
  expect(repository.importFinancialEvents.mock.calls[0][0]).toHaveLength(1)
  expect(repository.importFinancialEvents.mock.calls[0][0][0].event.source).toBe('Extrato fictício')
  expect(host.textContent).toContain('1 importadas e 0 duplicadas ignoradas')
})
