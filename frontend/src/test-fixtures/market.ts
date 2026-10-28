import type { PortfolioValuation } from '../api'

// Fictional, deterministic backend contract; never queried from a real provider.
export function marketSnapshot(status: PortfolioValuation['valuation']['status'] = 'complete'): PortfolioValuation {
  const time = '2026-10-28T16:00:00Z'
  const snapshot: PortfolioValuation = {
    ledger_as_of: time, acquisition_cost: '200', total_purchases: '200', sale_proceeds: '0', realized_profit: '0', market_value: '240',
    holdings: [{ ticker: 'ITUB4', quantity: '10', cost: '200', average_price: '20', average_trade_price: '20', purchase_cost_without_fees: '200', price_appreciation_percent: '20', market_value: '240', unrealized_profit: '40', return_percent: '20',
      quote: { ticker: 'ITUB4', price: '24', currency: 'BRL', provider: 'brapi', status: 'ok', reason: null, quoted_at: time,
        fetched_at: time, from_cache: false, is_stale: false, expected_delay_seconds: 1800, retry_after_seconds: null } }],
    valuation: { status, calculated_at: time, is_complete: true, open_cost: '200', unrealized_profit: '40', return_percent: '20',
      partial_market_value: '240', covered_cost: '200', covered_positions: 1, total_positions: 1,
      missing_tickers: [], quoted_at_min: time, quoted_at_max: time },
  }
  if (status === 'stale') {
    snapshot.holdings[0].quote = { ...snapshot.holdings[0].quote, status: 'stale', is_stale: true, from_cache: true, reason: 'network_error', quoted_at: '2026-10-28T13:00:00Z' }
    snapshot.valuation.quoted_at_min = '2026-10-28T13:00:00Z'
    snapshot.valuation.quoted_at_max = '2026-10-28T13:00:00Z'
  }
  if (status === 'partial' || status === 'unavailable') {
    const missing = structuredClone(snapshot.holdings[0])
    missing.ticker = missing.quote.ticker = status === 'partial' ? 'PETR4' : 'ITUB4'
    missing.quote = { ...missing.quote, status: 'no_data', reason: 'not_found', price: null, quoted_at: null }
    missing.market_value = missing.unrealized_profit = missing.return_percent = null
    missing.price_appreciation_percent = null
    snapshot.holdings = status === 'partial' ? [...snapshot.holdings, missing] : [missing]
    snapshot.market_value = null
    Object.assign(snapshot.valuation, { is_complete: false, unrealized_profit: null, return_percent: null,
      total_positions: snapshot.holdings.length, missing_tickers: [missing.ticker],
      covered_positions: status === 'partial' ? 1 : 0, partial_market_value: status === 'partial' ? '240' : '0',
      covered_cost: status === 'partial' ? '200' : '0', open_cost: status === 'partial' ? '400' : '200' })
    if (status === 'partial') snapshot.acquisition_cost = snapshot.total_purchases = '400'
    else snapshot.valuation.quoted_at_min = snapshot.valuation.quoted_at_max = null
  }
  if (status === 'empty') {
    snapshot.holdings = []
    snapshot.market_value = snapshot.acquisition_cost = snapshot.total_purchases = '0'
    Object.assign(snapshot.valuation, { open_cost: '0', unrealized_profit: '0', return_percent: null,
      partial_market_value: '0', covered_cost: '0', total_positions: 0, covered_positions: 0,
      quoted_at_min: null, quoted_at_max: null })
  }
  return snapshot
}
