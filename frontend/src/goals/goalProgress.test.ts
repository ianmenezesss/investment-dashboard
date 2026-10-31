import { expect, test } from 'vitest'
import type { FinancialPerformance } from '../api'
import { createGoal } from './goalStorage'
import { confirmManualProgress, deriveInvestedBasis, goalForDisplay, setGoalToInvested } from './goalProgress'

const goal = createGoal({ name: 'Reserva', targetAmount: '10000', targetDate: null, initialReferenceAmount: '100' }, new Date('2026-10-30T12:00:00Z'))
const performance = (overrides: Record<string, unknown> = {}) => ({
  as_of: '2026-10-30',
  flows: { recorded_contributions: '99999.99', net_recorded_flow: '99999.99' },
  capital: { basis: 'equity_open_acquisition_cost_plus_effective_cdb_principal', open_positions_accounted: '1250.55' },
  fixed_income: { missing_positions: [], declared_positions: [] },
  composition: { as_of: '2026-10-30', missing_fixed_income: [], declared_positions: [], missing_components: ['cotações de mercado para ações'] },
  ...overrides,
}) as unknown as FinancialPerformance

test('uses only the explicitly defined open-position capital basis and ignores external cash-flow totals', () => {
  expect(deriveInvestedBasis(performance(), false, false)).toMatchObject({ status: 'available', amount: '1250.55', asOf: '2026-10-30', warnings: [] })
})

test('marks declared and unaccounted fixed-income positions as partial and permits a manual fallback', () => {
  const snapshot = performance({
    fixed_income: { missing_positions: ['CDB sem lote'] },
    composition: { as_of: '2026-10-30', missing_fixed_income: ['CDB sem lote'], declared_positions: [{ asset: 'CDB observado' }], missing_components: ['posições sem lote nem observação'] },
  })
  const basis = deriveInvestedBasis(snapshot, false, false)
  expect(basis.status).toBe('partial')
  expect(basis.warnings).toEqual(expect.arrayContaining(['Renda fixa sem saldo apurado: CDB sem lote', 'Posição declarada excluída da base: CDB observado', 'posições sem lote nem observação']))
  const invested = goalForDisplay(setGoalToInvested(goal), basis)
  expect(invested.currentAmount).toBe('1250.55')
  expect(invested.manualProgressAmount).toBe('100.00')
})

test('keeps manual progress visible when the performance endpoint is unavailable', () => {
  expect(deriveInvestedBasis(undefined, false, true)).toMatchObject({ status: 'unavailable', amount: null })
  expect(goalForDisplay(setGoalToInvested(goal), deriveInvestedBasis(undefined, false, true)).currentAmount).toBe('100.00')
  expect(deriveInvestedBasis(undefined, true, false).status).toBe('loading')
})

test('confirms manual snapshots, rounds cents, switches source and rejects negative or excessive values', () => {
  const now = new Date('2026-11-01T12:00:00Z')
  const confirmed = confirmManualProgress(setGoalToInvested(goal), '999.999', now)
  expect(confirmed).toMatchObject({ currentAmount: '1000.00', manualProgressAmount: '1000.00', progressSource: 'manual', manualConfirmedAt: now.toISOString() })
  expect(() => confirmManualProgress(goal, '-1', now)).toThrow('entre R$ 0')
  expect(() => confirmManualProgress(goal, '1000000000001', now)).toThrow('entre R$ 0')
})
