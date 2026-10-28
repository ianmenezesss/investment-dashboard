import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, test, vi } from 'vitest'
import { MarketDashboard } from './MarketDashboard'
import { marketSnapshot } from '../test-fixtures/market'
import { marketMoney, marketPercent, marketQuantity } from './market-format'

const disposers: (() => Promise<void>)[] = []
afterEach(async () => { for (const dispose of disposers.splice(0)) await dispose() })
async function render(snapshot = marketSnapshot(), updating = false, failed = false) {
  const host = document.createElement('div'); document.body.appendChild(host)
  const root = createRoot(host), refresh = vi.fn()
  await act(async () => root.render(<MarketDashboard snapshot={snapshot} updating={updating} failed={failed} onRefresh={refresh}/>))
  disposers.push(async () => { await act(async () => root.unmount()); host.remove() })
  return { host, refresh }
}

test('completo mostra o mesmo snapshot, estimativa, variação, cotação e horários', async () => {
  const { host } = await render()
  expect(host.textContent).toContain('Cobertura completa')
  expect(host.textContent).toContain('Patrimônio a mercado · estimativa')
  const cards = host.querySelectorAll('.market-metrics article')
  expect(cards[0].textContent).toContain('R$ 240,00')
  expect(cards[1].textContent).toContain('R$ 40,00')
  expect(cards[2].textContent).toContain('20,00%')
  expect(host.textContent).toContain('não são em tempo real')
  expect(host.querySelector('tbody')!.textContent).toContain('R$ 24,00')
  expect(host.querySelector('tbody')!.textContent).toContain('R$ 20,00')
  expect(host.textContent).toContain('Fonte: brapi')
  expect(host.querySelector('time')!.dateTime).toBe('2026-10-28T16:00:00Z')
  expect(host.textContent).toContain('13:00 (Brasília)')
  expect(host.querySelector('caption')!.textContent).toContain('mesmo snapshot')
})

test('parcial não substitui totais null pelo subtotal nem por zero', async () => {
  const { host } = await render(marketSnapshot('partial'))
  expect(host.textContent).toContain('Cobertura parcial')
  expect(host.textContent).toContain('1 de 2 posições')
  for (const card of host.querySelectorAll('.market-metrics article')) expect(card.textContent).toContain('Indisponível')
  expect(host.querySelector('.market-partial')!.textContent).toContain('R$ 240,00')
  expect(host.querySelector('.market-partial')!.textContent).toContain('Não representa o patrimônio total')
  expect(host.querySelector('.market-partial')!.textContent).toContain('PETR4')
})

test('desatualizado mantém preços estimados, fonte, cache e referência original', async () => {
  const { host } = await render(marketSnapshot('stale'))
  expect(host.textContent).toContain('Avaliação desatualizada')
  expect(host.textContent).toContain('R$ 240,00')
  expect(host.textContent).toContain('cache do servidor')
  expect(host.querySelector('time[datetime="2026-10-28T13:00:00Z"]')).not.toBeNull()
})

test('indisponível preserva custo e não inventa mercado', async () => {
  const { host } = await render(marketSnapshot('unavailable'))
  expect(host.textContent).toContain('Cotações indisponíveis')
  expect(host.querySelector('.market-metrics article')!.textContent).toContain('Indisponível')
  expect(host.querySelector('tbody')!.textContent).toContain('R$ 200,00')
  expect(host.querySelector('tbody')!.textContent).toContain('Horário indisponível')
})

test('carteira vazia tem zero real e percentual ausente, sem confundir com preço faltante', async () => {
  const { host } = await render(marketSnapshot('empty'))
  expect(host.textContent).toContain('Sem posições abertas')
  const cards = host.querySelectorAll('.market-metrics article')
  expect(cards[0].textContent).toContain('R$ 0,00')
  expect(cards[1].textContent).toContain('R$ 0,00')
  expect(cards[2].textContent).toContain('Indisponível')
  expect(host.querySelector('table')).toBeNull()
})

test('erro de atualização mantém snapshot explicitamente anterior, com tentativa manual', async () => {
  const { host, refresh } = await render(marketSnapshot(), false, true)
  expect(host.textContent).toContain('sem confirmação de atualização')
  expect(host.textContent).toContain('R$ 240,00')
  await act(async () => (host.querySelector('button') as HTMLButtonElement).click())
  expect(refresh).toHaveBeenCalledOnce()
})

test('atualização pendente não desmonta valores nem permite cliques repetidos', async () => {
  const { host } = await render(marketSnapshot(), true)
  expect((host.querySelector('button') as HTMLButtonElement).disabled).toBe(true)
  expect(host.textContent).toContain('valores anteriores')
  expect(host.textContent).toContain('R$ 240,00')
})

test('prejuízo usa sinal e texto, sem depender somente da cor', async () => {
  const s = marketSnapshot()
  s.holdings[0].quote.price = '10'
  s.valuation.partial_market_value = '100'
  s.market_value = s.holdings[0].market_value = '100'
  s.valuation.unrealized_profit = s.holdings[0].unrealized_profit = '-100'
  s.valuation.return_percent = s.holdings[0].return_percent = '-50'
  const { host } = await render(s)
  expect(host.textContent).toContain('-R$ 100,00')
  expect(host.textContent).toContain('-50,00%')
})

test('formatação decimal não perde precisão nem converte null em zero', () => {
  expect(marketMoney('9007199254740993.005')).toBe('R$ 9.007.199.254.740.993,00')
  expect(marketMoney('0.295')).toBe('R$ 0,30')
  expect(marketMoney('0.285')).toBe('R$ 0,28')
  expect(marketMoney(null)).toBe('Indisponível')
  expect(marketMoney('NaN')).toBe('Indisponível')
  expect(marketPercent('0')).toBe('0,00%')
  expect(marketQuantity('10.01000000')).toBe('10,01')
  expect(marketQuantity('10')).toBe('10')
})

test('estado parcial bloqueia um total conflitante recebido por engano', async () => {
  const s = marketSnapshot('partial'); s.market_value = '999999'
  const { host } = await render(s)
  expect(host.querySelector('.market-metrics')!.textContent).not.toContain('999.999')
})
