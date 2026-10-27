export type Operation = { id: number; ticker: string; kind: 'BUY' | 'SELL'; date: string; quantity: string; price: string; fees: string }
export type Summary = { acquisition_cost: string; total_purchases: string; sale_proceeds: string; realized_profit: string; market_value: null; holdings: { ticker: string; quantity: string; cost: string; average_price: string }[] }
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
