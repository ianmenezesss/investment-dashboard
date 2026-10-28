export type Operation = { id: number; ticker: string; kind: 'BUY' | 'SELL'; date: string; quantity: string; price: string; fees: string }
export type Summary = { acquisition_cost: string; total_purchases: string; sale_proceeds: string; realized_profit: string; market_value: null; holdings: { ticker: string; quantity: string; cost: string; average_price: string }[] }
export type MarketQuote = {
  ticker: string; price: string | null; currency: string; provider: string
  status: 'ok' | 'stale' | 'no_data' | 'provider_error' | 'unavailable' | 'disabled'
  reason: string | null; quoted_at: string | null; fetched_at: string | null
  from_cache: boolean; is_stale: boolean; expected_delay_seconds: number; retry_after_seconds: number | null
}
export type ValuedHolding = Summary['holdings'][number] & {
  purchase_cost_without_fees?: string | null; average_trade_price?: string | null; price_appreciation_percent?: string | null
  quote: MarketQuote; market_value: string | null; unrealized_profit: string | null; return_percent: string | null
}
export type PortfolioValuation = Omit<Summary, 'market_value' | 'holdings'> & {
  ledger_as_of: string; market_value: string | null; holdings: ValuedHolding[]
  valuation: {
    status: 'complete' | 'stale' | 'partial' | 'unavailable' | 'empty'
    calculated_at: string; is_complete: boolean; open_cost: string
    unrealized_profit: string | null; return_percent: string | null
    partial_market_value: string; covered_cost: string; covered_positions: number; total_positions: number
    missing_tickers: string[]; quoted_at_min: string | null; quoted_at_max: string | null
  }
}
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
export async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  if (PUBLIC_DEMO) throw new Error('A demonstração pública não acessa a API privada.')
  if (!token) throw new ApiError(401, 'Entre para acessar sua carteira.')
  const response = await fetch(`${apiBase()}/api/${path}`, { ...init, cache: 'no-store', credentials: 'omit', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, response.status === 401 ? 'Sessão inválida ou expirada. Entre novamente.' : response.status === 403 ? 'Sua conta não está autorizada a acessar esta carteira.' : typeof body.detail === 'string' ? body.detail : `Não foi possível concluir a solicitação (${response.status}). Confira os campos e a conexão com a API.`)
  }
  return response.status === 204 ? undefined as T : response.json()
}
import { apiBase, PUBLIC_DEMO } from './runtime'
