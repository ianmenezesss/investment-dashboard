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

test('distingue valorização sem taxas de perda financeira e mantém ajuda acessível', async () => {
  const snapshot = marketSnapshot()
  Object.assign(snapshot.holdings[0], { average_trade_price: '20', average_price: '22', cost: '220',
    market_value: '210', unrealized_profit: '-10', return_percent: '-4.54545', price_appreciation_percent: '5' })
  snapshot.holdings[0].quote.price = '21'
  const { host } = await render(snapshot)
  const row = host.querySelector('tbody')!
  expect(row.textContent).toContain('R$ 20,00')
  expect(row.textContent).toContain('R$ 22,00')
  expect(row.textContent).toContain('5,00%')
  expect(row.textContent).toContain('-R$ 10,00')
  expect(row.textContent).toContain('-4,55%')
  expect(host.textContent).toContain('tributos futuros')
  const help = host.querySelector<HTMLButtonElement>('button[aria-label="Entender: preço de compra"]')!
  await act(async () => help.focus())
  const tooltip = document.getElementById(help.getAttribute('aria-describedby')!)!
  expect(tooltip.getAttribute('role')).toBe('tooltip')
  expect(tooltip.textContent).toContain('Vendas parciais reduzem a base proporcionalmente')
  await act(async () => help.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(document.querySelector('[role="tooltip"]')).toBeNull()
  await act(async () => help.click())
  expect(document.querySelector('[role="tooltip"]')).not.toBeNull()
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(document.querySelector('[role="tooltip"]')).toBeNull()
})

test('resposta anterior sem base sem taxas não inventa preço nem valorização', async () => {
  const snapshot = marketSnapshot()
  delete snapshot.holdings[0].average_trade_price
  delete snapshot.holdings[0].price_appreciation_percent
  const { host } = await render(snapshot)
  const cells = host.querySelectorAll('tbody td')
  expect(cells[1].textContent).toContain('Indisponível')
  expect(cells[5].textContent).toContain('Indisponível')
  expect(cells[2].textContent).toContain('R$ 20,00')
})

test('exibe bases remanescentes de compras múltiplas e venda parcial recebidas do backend', async () => {
  const snapshot = marketSnapshot()
  Object.assign(snapshot.holdings[0], { quantity: '20', average_trade_price: '25', average_price: '25.325',
    cost: '506.5', purchase_cost_without_fees: '500', market_value: '600', unrealized_profit: '93.5',
    return_percent: '18.4600197433', price_appreciation_percent: '20' })
  snapshot.holdings[0].quote.price = '30'
  const { host } = await render(snapshot)
  const row = host.querySelector('tbody')!
  expect(row.textContent).toContain('R$ 25,00')
  expect(row.textContent).toContain('R$ 25,32') // half-even, presentation only
  expect(row.textContent).toContain('R$ 93,50')
  expect(row.textContent).toContain('20,00%')
  expect(row.textContent).toContain('18,46%')
})

test('sem cotação preserva média negociada mas omite valorização mesmo em resposta incoerente', async () => {
  const snapshot = marketSnapshot('unavailable')
  snapshot.holdings[0].price_appreciation_percent = '20'
  const { host } = await render(snapshot)
  const cells = host.querySelectorAll('tbody td')
  expect(cells[1].textContent).toContain('R$ 20,00')
  expect(cells[5].textContent).toContain('Indisponível')
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
