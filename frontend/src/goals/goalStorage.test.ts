import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createGoal, goalProgressPercent, goalState, goalsStorageKey, loadGoals, saveGoals, updateGoal, validateGoalDraft } from './goalStorage'

const draft = { name: 'Casa', targetAmount: '100000', targetDate: '2030-12-31', initialReferenceAmount: '1250.50' }
const now = new Date('2026-10-30T12:00:00.000Z')

beforeEach(() => vi.stubGlobal('crypto', { randomUUID: () => 'goal-id' }))
afterEach(() => vi.unstubAllGlobals())

test('validates and normalizes drafts and creates an initial manual reference', () => {
  expect(validateGoalDraft({ ...draft, name: '  Casa  ' })).toEqual({ ...draft, name: 'Casa', targetAmount: '100000.00', initialReferenceAmount: '1250.50' })
  expect(createGoal(draft, now)).toMatchObject({ id: 'goal-id', currentAmount: '1250.50', initialReferenceAmount: '1250.50', progressSource: 'manual', manualConfirmedAt: now.toISOString(), createdAt: now.toISOString() })
})

test('rejects invalid names, nonpositive or out-of-range targets, invalid dates, and a target rounded below one cent', () => {
  expect(() => validateGoalDraft({ ...draft, name: ' ' })).toThrow('nome')
  expect(() => validateGoalDraft({ ...draft, targetAmount: '0' })).toThrow('Valor-alvo')
  expect(() => validateGoalDraft({ ...draft, targetAmount: '0.001' })).toThrow('mínimo')
  expect(() => validateGoalDraft({ ...draft, targetAmount: '1000000000001' })).toThrow('Valor-alvo')
  expect(() => validateGoalDraft({ ...draft, targetDate: '2026-02-30' })).toThrow('Prazo')
  expect(validateGoalDraft({ ...draft, targetDate: '' }).targetDate).toBeNull()
})

test('uses completion, overdue, active and no-deadline states and caps progress at 100 percent', () => {
  const goal = createGoal(draft, now)
  expect(goalState(goal, new Date('2026-10-30T12:00:00Z'))).toBe('active')
  expect(goalState({ ...goal, targetDate: null }, now)).toBe('no-deadline')
  expect(goalState({ ...goal, targetDate: '2026-10-29' }, now)).toBe('overdue')
  expect(goalState({ ...goal, currentAmount: '100000.00' }, now)).toBe('completed')
  expect(goalProgressPercent({ ...goal, currentAmount: '150000' })).toBe(100)
  expect(goalProgressPercent({ ...goal, currentAmount: '12345' })).toBe(12.3)
})

test('stores per identity, updates only goal metadata and can preserve independent profiles', () => {
  const memory = new Map<string, string>()
  const storage = { getItem: (key: string) => memory.get(key) ?? null, setItem: (key: string, value: string) => { memory.set(key, value) } }
  const goal = createGoal(draft, now)
  saveGoals('owner-a', [goal], storage)
  expect(loadGoals('owner-a', storage)).toEqual([goal])
  expect(loadGoals('owner-b', storage)).toEqual([])
  const updated = updateGoal(goal, { ...draft, name: 'Casa nova', targetAmount: '150000' }, new Date('2026-11-01T12:00:00Z'))
  expect(updated).toMatchObject({ currentAmount: '1250.50', initialReferenceAmount: '1250.50', name: 'Casa nova', targetAmount: '150000.00' })
  expect(goalsStorageKey('owner/a')).not.toBe(goalsStorageKey('owner-a'))
})

test('does not overwrite malformed or incompatible local records', () => {
  const memory = new Map<string, string>([[goalsStorageKey('owner-a'), '{bad json']])
  const storage = { getItem: (key: string) => memory.get(key) ?? null, setItem: vi.fn((key: string, value: string) => { memory.set(key, value) }) }
  expect(() => loadGoals('owner-a', storage)).toThrow('preservados')
  expect(() => saveGoals('owner-a', [{ id: 'bad' } as never], storage)).toThrow()
  expect(memory.get(goalsStorageKey('owner-a'))).toBe('{bad json')
  expect(storage.setItem).not.toHaveBeenCalled()
})
