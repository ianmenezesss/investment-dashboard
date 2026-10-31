import Decimal from 'decimal.js'
import type { FinancialPerformance } from '../api'
import { type Goal } from './goalStorage'

export type InvestedBasis = {
  status: 'available' | 'partial' | 'unavailable' | 'loading'
  amount: string | null
  asOf: string | null
  warnings: string[]
}

export function deriveInvestedBasis(performance: FinancialPerformance | undefined, loading: boolean, failed: boolean): InvestedBasis {
  if (!performance) return { status: loading ? 'loading' : 'unavailable', amount: null, asOf: null,
    warnings: [failed ? 'Dados das posições não puderam ser carregados.' : 'Dados de capital investido indisponíveis.'] }
  if (performance.capital?.basis !== 'equity_open_acquisition_cost_plus_effective_cdb_principal') {
    return { status: 'unavailable', amount: null, asOf: performance.as_of ?? null, warnings: ['A base de capital investido não foi reconhecida.'] }
  }
  let amount: Decimal
  try { amount = new Decimal(performance.capital.open_positions_accounted) } catch {
    return { status: 'unavailable', amount: null, asOf: performance.as_of ?? null, warnings: ['Valor contabilizado das posições inválido.'] }
  }
  if (!amount.isFinite() || amount.isNegative()) return { status: 'unavailable', amount: null, asOf: performance.as_of ?? null, warnings: ['Valor contabilizado das posições inválido.'] }
  const missing = new Set<string>()
  for (const asset of performance.fixed_income?.missing_positions ?? []) missing.add(`Renda fixa sem saldo apurado: ${asset}`)
  for (const asset of performance.composition?.missing_fixed_income ?? []) missing.add(`Renda fixa sem saldo apurado: ${asset}`)
  for (const position of performance.composition?.declared_positions ?? []) missing.add(`Posição declarada excluída da base: ${position.asset}`)
  for (const component of performance.composition?.missing_components ?? []) {
    if (!component.toLocaleLowerCase('pt-BR').includes('cotações de mercado')) missing.add(component)
  }
  return { status: missing.size ? 'partial' : 'available', amount: amount.toDecimalPlaces(2).toFixed(2),
    asOf: performance.as_of ?? performance.composition?.as_of ?? null, warnings: [...missing] }
}

export function goalForDisplay(goal: Goal, basis: InvestedBasis): Goal {
  if (goal.progressSource === 'invested' && basis.amount !== null) return { ...goal, currentAmount: basis.amount }
  return { ...goal, currentAmount: goal.manualProgressAmount }
}

export function setGoalToInvested(goal: Goal): Goal {
  return { ...goal, progressSource: 'invested', currentAmount: goal.manualProgressAmount, updatedAt: new Date().toISOString() }
}

export function confirmManualProgress(goal: Goal, rawAmount: string, now = new Date()): Goal {
  let amount: Decimal
  try { amount = new Decimal(rawAmount) } catch { throw new Error('Informe um valor manual válido.') }
  if (!amount.isFinite() || amount.isNegative() || amount.gt('1000000000000')) throw new Error('O progresso manual deve estar entre R$ 0 e R$ 1.000.000.000.000.')
  const formatted = amount.toDecimalPlaces(2).toFixed(2)
  return { ...goal, currentAmount: formatted, manualProgressAmount: formatted, progressSource: 'manual', manualConfirmedAt: now.toISOString(), updatedAt: now.toISOString() }
}
