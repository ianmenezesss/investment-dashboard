import { describe, expect, it } from 'vitest'
import { formatDailyAxisDate } from './chartDates'

describe('daily history chart date labels', () => {
  it('uses distinct day and month labels for the free three-month window', () => {
    const dates = ['2026-10-01', '2026-10-15', '2026-10-28', '2026-11-03']
    const labels = dates.map(formatDailyAxisDate)
    expect(labels.every(label => /\d{2}/.test(label))).toBe(true)
    expect(new Set(labels).size).toBe(dates.length)
  })
})
