import Decimal from 'decimal.js'
import { expect, test } from 'vitest'
import { simulateScenario } from '../simulator/simulation'
import { DEFAULT_GOAL_PLANNING, validateGoalPlanningSettings } from './goalStorage'
import { calculateGoalPlan, goalPlanningHorizon, requiredMonthlyContribution } from './planningMath'

const now = new Date(2026, 9, 30, 12)
const settings = (values: Partial<typeof DEFAULT_GOAL_PLANNING> = {}) => ({ ...DEFAULT_GOAL_PLANNING, ...values })

test('uses calendar months for a future target and a saved manual horizon for no-date or expired goals', () => {
  expect(goalPlanningHorizon('2027-10-30', settings(), now)).toMatchObject({ months: 12, horizon: 'deadline' })
  expect(goalPlanningHorizon('2026-10-31', settings(), now)).toMatchObject({ months: 1, horizon: 'deadline' })
  expect(goalPlanningHorizon('2026-10-30', settings({ horizonMonths: '24' }), now)).toMatchObject({ months: 24, horizon: 'today' })
  expect(goalPlanningHorizon(null, settings({ horizonMonths: '36' }), now)).toMatchObject({ months: 36, horizon: 'manual' })
  expect(goalPlanningHorizon('2026-10-01', settings({ horizonMonths: '24' }), now)).toMatchObject({ months: 24, horizon: 'expired' })
  expect(goalPlanningHorizon('2027-10-30', settings({ horizonMonths: '18', useManualHorizon: true }), now)).toMatchObject({ months: 18, horizon: 'manual' })
})

test('calculates the zero-return aporte and replays to the target using the simulator convention', () => {
  const rate = new Decimal(0)
  const monthly = requiredMonthlyContribution(new Decimal(100), new Decimal(1000), rate, 12)
  expect(monthly.toFixed(2)).toBe('75.00')
  const replay = simulateScenario({ initial: new Decimal(100), monthly, months: 12, inflation: new Decimal(0), includeInflation: false, timing: 'end' }, rate)
  expect(replay.finalNominal.toFixed(2)).toBe('1000.00')
  expect(calculateGoalPlan({ currentAmount: '100', targetAmount: '1000', targetDate: null,
    settings: settings({ horizonMonths: '12', monthlyContribution: '75', annualRates: { conservative: '0', moderate: '0', optimistic: '0' } }), now }).scenarios[0].projected.finalNominal.toFixed(2)).toBe('1000.00')
})

test('reuses the simulator effective annual-to-monthly rates and reports gap, required aportes, and time estimates', () => {
  const plan = calculateGoalPlan({ currentAmount: '1000', targetAmount: '10000', targetDate: '2027-10-30', settings: settings({ monthlyContribution: '300' }), now })
  expect(plan).toMatchObject({ months: 12, horizon: 'deadline' })
  expect(plan.gap.toFixed(2)).toBe('9000.00')
  for (const scenario of plan.scenarios) {
    const replay = simulateScenario({ initial: new Decimal(1000), monthly: scenario.requiredMonthly, months: 12, inflation: new Decimal(0), includeInflation: false, timing: 'end' }, scenario.annualRate)
    expect(replay.finalNominal.toDecimalPlaces(6).toNumber()).toBeCloseTo(10000, 3)
    expect(scenario.projected.finalNominal.isPositive()).toBe(true)
    expect(scenario.monthsToGoal).not.toBeNull()
  }
  expect(plan.chart).toHaveLength(13)
})

test('handles completed goals, zero aportes, negative hypotheses and the 600 month simulator limit', () => {
  const complete = calculateGoalPlan({ currentAmount: '1000', targetAmount: '900', targetDate: null, settings: settings({ horizonMonths: '1', monthlyContribution: '0' }), now })
  expect(complete.gap.toFixed(2)).toBe('0.00')
  expect(complete.scenarios.every(scenario => scenario.requiredMonthly.isZero() && scenario.monthsToGoal === 0)).toBe(true)
  const noGrowth = calculateGoalPlan({ currentAmount: '0', targetAmount: '1000', targetDate: null,
    settings: settings({ horizonMonths: '12', monthlyContribution: '0', annualRates: { conservative: '0', moderate: '0', optimistic: '0' } }), now })
  expect(noGrowth.scenarios[0].monthsToGoal).toBeNull()
  const negative = calculateGoalPlan({ currentAmount: '100', targetAmount: '1000', targetDate: null,
    settings: settings({ horizonMonths: '12', annualRates: { conservative: '-10', moderate: '0', optimistic: '14' } }), now })
  expect(negative.scenarios[0].requiredMonthly.isPositive()).toBe(true)
  expect(() => calculateGoalPlan({ currentAmount: '100', targetAmount: '1000', targetDate: null, settings: settings({ horizonMonths: '601' }), now })).toThrow('1 a 600')
})

test('validates aporte, horizon, and editable annual assumptions within simulator bounds', () => {
  expect(validateGoalPlanningSettings(settings({ monthlyContribution: '25.4', annualRates: { conservative: '0', moderate: '10.5', optimistic: '500' } }))).toMatchObject({ monthlyContribution: '25.40', annualRates: { moderate: '10.5', optimistic: '500' } })
  expect(() => validateGoalPlanningSettings(settings({ monthlyContribution: '-1' }))).toThrow('Aporte mensal')
  expect(() => validateGoalPlanningSettings(settings({ horizonMonths: '0' }))).toThrow('1 a 600')
  expect(() => validateGoalPlanningSettings(settings({ annualRates: { conservative: '-100', moderate: '10', optimistic: '14' } }))).toThrow('maior que -100%')
  expect(() => validateGoalPlanningSettings(settings({ annualRates: { conservative: '6', moderate: '10', optimistic: '501' } }))).toThrow('maior que -100%')
})
