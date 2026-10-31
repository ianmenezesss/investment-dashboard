import Decimal from 'decimal.js'
import { monthlyEffectiveRate, simulateScenario, type ScenarioResult } from '../simulator/simulation'
import { localDateString, validateGoalPlanningSettings, type GoalPlanningSettings } from './goalStorage'

export const MAX_GOAL_PROJECTION_MONTHS = 600
export type GoalScenarioKey = keyof GoalPlanningSettings['annualRates']
export type GoalScenario = { key: GoalScenarioKey; label: string; color: string; annualRate: Decimal; requiredMonthly: Decimal; monthsToGoal: number | null; projected: ScenarioResult }
export type GoalProjectionPoint = { month: number; baseAndContributions: number; conservative: number; moderate: number; optimistic: number }
export type GoalPlan = { gap: Decimal; months: number; horizon: 'deadline' | 'manual' | 'today' | 'expired'; scenarios: GoalScenario[]; chart: GoalProjectionPoint[] }

const scenarioMeta: Record<GoalScenarioKey, { label: string; color: string }> = {
  conservative: { label: 'Conservador', color: '#8298f8' },
  moderate: { label: 'Moderado', color: '#68e5b4' },
  optimistic: { label: 'Otimista', color: '#e8c77c' },
}

export function goalPlanningHorizon(targetDate: string | null, settings: GoalPlanningSettings, now = new Date()) {
  const today = localDateString(now)
  if (targetDate && targetDate > today && !settings.useManualHorizon) {
    const [targetYear, targetMonth] = targetDate.split('-').map(Number)
    const months = (targetYear - now.getFullYear()) * 12 + targetMonth - 1 - now.getMonth()
    return { months: Math.max(1, months), horizon: 'deadline' as const }
  }
  return { months: Number(settings.horizonMonths), horizon: targetDate && targetDate < today ? 'expired' as const : targetDate === today ? 'today' as const : 'manual' as const }
}

export function requiredMonthlyContribution(currentValue: Decimal, targetValue: Decimal, annualRate: Decimal, months: number) {
  if (!Number.isInteger(months) || months < 1 || months > MAX_GOAL_PROJECTION_MONTHS) throw new RangeError('O horizonte deve estar entre 1 e 600 meses.')
  const monthlyRate = monthlyEffectiveRate(annualRate)
  const growth = new Decimal(1).plus(monthlyRate).pow(months)
  const balanceAtHorizonWithoutContributions = currentValue.mul(growth)
  if (balanceAtHorizonWithoutContributions.gte(targetValue)) return new Decimal(0)
  const remainingAtHorizon = targetValue.minus(balanceAtHorizonWithoutContributions)
  if (monthlyRate.isZero()) return Decimal.max(0, remainingAtHorizon.div(months))
  const endOfMonthAnnuityFactor = growth.minus(1).div(monthlyRate)
  return Decimal.max(0, remainingAtHorizon.div(endOfMonthAnnuityFactor))
}

function monthsToGoal(current: Decimal, target: Decimal, monthly: Decimal, annualRate: Decimal) {
  if (current.gte(target)) return 0
  const result = simulateScenario({ initial: current, monthly, months: MAX_GOAL_PROJECTION_MONTHS, inflation: new Decimal(0), includeInflation: false, timing: 'end' }, annualRate)
  return result.points.find(point => point.month > 0 && point.balanceNominal.gte(target))?.month ?? null
}

export function calculateGoalPlan(input: { currentAmount: string; targetAmount: string; targetDate: string | null; settings: GoalPlanningSettings; now?: Date }): GoalPlan {
  const settings = validateGoalPlanningSettings(input.settings)
  const current = new Decimal(input.currentAmount)
  const target = new Decimal(input.targetAmount)
  if (!current.isFinite() || current.isNegative() || !target.isFinite() || !target.isPositive()) throw new Error('Confira o progresso atual e o valor-alvo da meta.')
  const { months, horizon } = goalPlanningHorizon(input.targetDate, settings, input.now)
  if (!Number.isInteger(months) || months < 1 || months > MAX_GOAL_PROJECTION_MONTHS) throw new RangeError('Para projetar, escolha um horizonte entre 1 e 600 meses.')
  const monthly = new Decimal(settings.monthlyContribution)
  const scenarios = (['conservative', 'moderate', 'optimistic'] as const).map(key => {
    const annualRate = new Decimal(settings.annualRates[key])
    const projected = simulateScenario({ initial: current, monthly, months, inflation: new Decimal(0), includeInflation: false, timing: 'end' }, annualRate)
    return { key, ...scenarioMeta[key], annualRate, requiredMonthly: requiredMonthlyContribution(current, target, annualRate, months),
      monthsToGoal: monthsToGoal(current, target, monthly, annualRate), projected }
  })
  const chart = Array.from({ length: months + 1 }, (_, month) => ({
    month,
    baseAndContributions: scenarios[0].projected.points[month].investedNominal.toNumber(),
    conservative: scenarios[0].projected.points[month].balanceNominal.toNumber(),
    moderate: scenarios[1].projected.points[month].balanceNominal.toNumber(),
    optimistic: scenarios[2].projected.points[month].balanceNominal.toNumber(),
  }))
  return { gap: Decimal.max(0, target.minus(current)), months, horizon, scenarios, chart }
}
