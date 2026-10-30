import Decimal from 'decimal.js'

export type Timing = 'beginning' | 'end'
export type SimulationInput = { initial: Decimal; monthly: Decimal; months: number; inflation: Decimal; includeInflation: boolean; timing: Timing }
export type SimulationPoint = { month: number; investedNominal: Decimal; investedReal: Decimal; balanceNominal: Decimal; balanceReal: Decimal }
export type ScenarioResult = { annualRate: Decimal; monthlyRate: Decimal; totalInvested: Decimal; totalInvestedReal: Decimal; finalNominal: Decimal; finalReal: Decimal; gainNominal: Decimal; gainReal: Decimal; points: SimulationPoint[] }

function safeDecimal(value: string) {
  try { return new Decimal(value || 'NaN') } catch { return new Decimal(Number.NaN) }
}

export function monthlyEffectiveRate(annualPercent: Decimal) {
  if (annualPercent.lte(-100)) throw new RangeError('A taxa anual deve ser maior que -100%.')
  return new Decimal(1).plus(annualPercent.div(100)).pow(new Decimal(1).div(12)).minus(1)
}

export function validateInputs(input: { initial: string; monthly: string; months: string; inflation: string; includeInflation: boolean }) {
  const errors: string[] = []
  const validDecimal = (value: string, label: string, min: number, max: number) => {
    const n = safeDecimal(value)
    if (!n.isFinite() || n.lt(min) || n.gt(max)) errors.push(`${label}: informe um valor entre ${min} e ${max}.`)
    return n
  }
  const initial = validDecimal(input.initial, 'Valor inicial', 0, 1_000_000_000)
  const monthly = validDecimal(input.monthly, 'Aporte mensal', 0, 100_000_000)
  const term = safeDecimal(input.months)
  if (!term.isInteger() || term.lt(1) || term.gt(600)) errors.push('Prazo: informe de 1 a 600 meses inteiros.')
  const inflation = input.includeInflation ? validDecimal(input.inflation, 'Inflação anual', 0, 1000) : new Decimal(0)
  return { valid: errors.length === 0, errors, initial, monthly, months: term.toNumber(), inflation }
}

export function simulateScenario(input: SimulationInput, annualPercent: Decimal): ScenarioResult {
  const monthlyRate = monthlyEffectiveRate(annualPercent)
  const inflationMonthly = input.includeInflation ? monthlyEffectiveRate(input.inflation) : new Decimal(0)
  let balance = input.initial
  let invested = input.initial
  let investedReal = input.initial
  const points: SimulationPoint[] = [{ month: 0, investedNominal: invested, investedReal, balanceNominal: balance, balanceReal: balance }]
  for (let month = 1; month <= input.months; month += 1) {
    if (input.timing === 'beginning') balance = balance.plus(input.monthly)
    balance = balance.mul(new Decimal(1).plus(monthlyRate))
    if (input.timing === 'end') balance = balance.plus(input.monthly)
    invested = invested.plus(input.monthly)
    const elapsed = input.months - month + (input.timing === 'beginning' ? 1 : 0)
    if (input.includeInflation && !input.monthly.isZero()) investedReal = investedReal.plus(input.monthly.div(new Decimal(1).plus(inflationMonthly).pow(elapsed)))
    else if (!input.monthly.isZero()) investedReal = investedReal.plus(input.monthly)
    const deflator = input.includeInflation ? new Decimal(1).plus(inflationMonthly).pow(month) : new Decimal(1)
    points.push({ month, investedNominal: invested, investedReal, balanceNominal: balance, balanceReal: balance.div(deflator) })
  }
  return { annualRate: annualPercent, monthlyRate, totalInvested: invested, totalInvestedReal: investedReal,
    finalNominal: balance, finalReal: points[points.length - 1].balanceReal,
    gainNominal: balance.minus(invested), gainReal: points[points.length - 1].balanceReal.minus(investedReal), points }
}
