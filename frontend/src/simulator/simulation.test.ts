import Decimal from 'decimal.js'
import { describe, expect, it } from 'vitest'
import { monthlyEffectiveRate, simulateScenario, validateInputs, type SimulationInput } from './simulation'

const scenario = (overrides: Partial<SimulationInput> = {}): SimulationInput => ({ initial: new Decimal(0), monthly: new Decimal(100), months: 12,
  inflation: new Decimal(0), includeInflation: false, timing: 'end', ...overrides })
const rate = (value: string) => new Decimal(value)

describe('investment simulation', () => {
  it('uses total contributions when return is zero and supports zero initial or monthly amounts', () => {
    const result = simulateScenario(scenario({ initial: new Decimal(250), monthly: new Decimal(0) }), rate('0'))
    expect(result.finalNominal.toFixed(2)).toBe('250.00')
    expect(result.totalInvested.toFixed(2)).toBe('250.00')
    expect(result.gainNominal.toFixed(2)).toBe('0.00')
    const noInitial = simulateScenario(scenario({ initial: new Decimal(0), monthly: new Decimal(50), months: 4 }), rate('0'))
    expect(noInitial.finalNominal.toFixed(2)).toBe('200.00')
  })
  it('converts annual effective rate to equivalent monthly rate and supports different terms', () => {
    expect(monthlyEffectiveRate(rate('12')).plus(1).pow(12).minus(1).toDecimalPlaces(8).toNumber()).toBe(0.12)
    const six = simulateScenario(scenario({ initial: new Decimal(1000), monthly: new Decimal(0), months: 6 }), rate('12'))
    const twelve = simulateScenario(scenario({ initial: new Decimal(1000), monthly: new Decimal(0), months: 12 }), rate('12'))
    expect(six.finalNominal.gt(1000)).toBe(true)
    expect(twelve.finalNominal.gt(six.finalNominal)).toBe(true)
    expect(twelve.points).toHaveLength(13)
  })
  it('accepts negative annual rates above -100 percent', () => {
    const result = simulateScenario(scenario({ initial: new Decimal(1000), monthly: new Decimal(0) }), rate('-12'))
    expect(result.finalNominal.lt(1000)).toBe(true)
    expect(() => monthlyEffectiveRate(rate('-100'))).toThrow(RangeError)
  })
  it('distinguishes contributions at beginning from contributions at end of month', () => {
    const end = simulateScenario(scenario(), rate('12'))
    const beginning = simulateScenario(scenario({ timing: 'beginning' }), rate('12'))
    expect(beginning.finalNominal.gt(end.finalNominal)).toBe(true)
    expect(beginning.totalInvested.eq(end.totalInvested)).toBe(true)
  })
  it('shows nominal and inflation-adjusted values as separate measures', () => {
    const result = simulateScenario(scenario({ initial: new Decimal(1000), monthly: new Decimal(100), months: 12, includeInflation: true, inflation: new Decimal(6) }), rate('10'))
    expect(result.finalNominal.gt(result.finalReal)).toBe(true)
    expect(result.totalInvested.toFixed(2)).toBe('2200.00')
    expect(result.totalInvestedReal.lt(result.totalInvested)).toBe(true)
  })
  it('compares different editable scenario rates deterministically', () => {
    const results = ['5', '10', '15'].map(value => simulateScenario(scenario({ initial: new Decimal(500), months: 24 }), rate(value)))
    expect(results[0].finalNominal.lt(results[1].finalNominal)).toBe(true)
    expect(results[1].finalNominal.lt(results[2].finalNominal)).toBe(true)
  })
  it('rejects invalid ranges, noninteger terms, and malformed inputs', () => {
    expect(validateInputs({ initial: '-1', monthly: '0', months: '12.5', inflation: '1001', includeInflation: true }).valid).toBe(false)
    expect(validateInputs({ initial: '0', monthly: '0', months: '1', inflation: '0', includeInflation: false }).valid).toBe(true)
    expect(validateInputs({ initial: '0', monthly: '0', months: '1', inflation: 'invalid', includeInflation: false }).valid).toBe(true)
    expect(validateInputs({ initial: '0', monthly: '0', months: '1', inflation: 'invalid', includeInflation: true }).valid).toBe(false)
  })
})
