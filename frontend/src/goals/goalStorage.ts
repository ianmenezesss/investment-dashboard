import Decimal from 'decimal.js'

export type Goal = {
  id: string
  name: string
  targetAmount: string
  targetDate: string | null
  initialReferenceAmount: string
  manualProgressAmount: string
  currentAmount: string
  progressSource: 'manual' | 'invested'
  manualConfirmedAt: string | null
  createdAt: string
  updatedAt: string
}

export type GoalDraft = Omit<Goal, 'id' | 'currentAmount' | 'manualProgressAmount' | 'progressSource' | 'manualConfirmedAt' | 'createdAt' | 'updatedAt'>
export type GoalStorage = Pick<Storage, 'getItem' | 'setItem'>
const KEY_PREFIX = 'investment-private-goals-v1:'
const MAX_TARGET = new Decimal('1000000000000')

export function goalsStorageKey(identity: string) { return `${KEY_PREFIX}${encodeURIComponent(identity)}` }

function amount(value: string, label: string, allowZero: boolean) {
  let parsed: Decimal
  try { parsed = new Decimal(value) } catch { throw new Error(`${label}: informe um valor numérico válido.`) }
  if (!parsed.isFinite() || (allowZero ? parsed.isNegative() : !parsed.isPositive()) || parsed.gt(MAX_TARGET)) {
    throw new Error(`${label}: informe um valor ${allowZero ? 'entre zero e' : 'maior que zero, até'} R$ 1.000.000.000.000.`)
  }
  const rounded = parsed.toDecimalPlaces(2)
  if (!allowZero && rounded.isZero()) throw new Error(`${label}: o valor mínimo é R$ 0,01.`)
  return rounded.toFixed(2)
}

function validDate(value: string | null) {
  if (value === null || value === '') return null
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Prazo: informe uma data válida ou deixe sem prazo.')
  const date = new Date(`${value}T12:00:00`)
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new Error('Prazo: informe uma data válida ou deixe sem prazo.')
  return value
}

export function validateGoalDraft(input: GoalDraft): GoalDraft {
  const name = input.name.trim()
  if (name.length < 2 || name.length > 80) throw new Error('O nome deve ter entre 2 e 80 caracteres.')
  return { name, targetAmount: amount(input.targetAmount, 'Valor-alvo', false), targetDate: validDate(input.targetDate),
    initialReferenceAmount: amount(input.initialReferenceAmount, 'Valor inicial de referência', true) }
}

export function createGoal(draft: GoalDraft, now = new Date()): Goal {
  const valid = validateGoalDraft(draft)
  return { ...valid, id: globalThis.crypto?.randomUUID?.() ?? `${now.getTime()}-${Math.random().toString(36).slice(2)}`,
    manualProgressAmount: valid.initialReferenceAmount, currentAmount: valid.initialReferenceAmount, progressSource: 'manual', manualConfirmedAt: now.toISOString(),
    createdAt: now.toISOString(), updatedAt: now.toISOString() }
}

export function updateGoal(goal: Goal, draft: GoalDraft, now = new Date()): Goal {
  return { ...goal, ...validateGoalDraft(draft), updatedAt: now.toISOString() }
}

export function validateStoredGoals(value: unknown): Goal[] {
  if (!Array.isArray(value) || value.length > 500) throw new Error('Os dados locais das metas estão em formato incompatível. Eles foram preservados.')
  const ids = new Set<string>()
  return value.map(item => {
    if (!item || typeof item !== 'object') throw new Error('Os dados locais das metas estão em formato incompatível. Eles foram preservados.')
    const goal = item as Goal
    const valid = validateGoalDraft({ name: goal.name, targetAmount: goal.targetAmount, targetDate: goal.targetDate,
      initialReferenceAmount: goal.initialReferenceAmount })
    if (typeof goal.id !== 'string' || !goal.id || !['manual', 'invested'].includes(goal.progressSource) ||
      typeof goal.currentAmount !== 'string' || typeof goal.manualProgressAmount !== 'string' || typeof goal.createdAt !== 'string' || typeof goal.updatedAt !== 'string' ||
      (goal.manualConfirmedAt !== null && typeof goal.manualConfirmedAt !== 'string')) {
      throw new Error('Os dados locais das metas estão em formato incompatível. Eles foram preservados.')
    }
    if (ids.has(goal.id) || !Number.isFinite(Date.parse(goal.createdAt)) || !Number.isFinite(Date.parse(goal.updatedAt)) ||
      (goal.manualConfirmedAt !== null && !Number.isFinite(Date.parse(goal.manualConfirmedAt)))) {
      throw new Error('Os dados locais das metas estão em formato incompatível. Eles foram preservados.')
    }
    ids.add(goal.id)
    const currentAmount = amount(goal.currentAmount, 'Progresso atual', true)
    const manualProgressAmount = amount(goal.manualProgressAmount, 'Progresso manual salvo', true)
    return { ...goal, ...valid, currentAmount, manualProgressAmount }
  })
}

export function loadGoals(identity: string, storage: GoalStorage = window.localStorage): Goal[] {
  const raw = storage.getItem(goalsStorageKey(identity))
  if (raw === null) return []
  try { return validateStoredGoals(JSON.parse(raw)) }
  catch (error) { if (error instanceof SyntaxError) throw new Error('Os dados locais das metas não puderam ser lidos e foram preservados.') ; throw error }
}

export function saveGoals(identity: string, goals: Goal[], storage: GoalStorage = window.localStorage) {
  storage.setItem(goalsStorageKey(identity), JSON.stringify(validateStoredGoals(goals)))
}

export function goalState(goal: Goal, now = new Date()) {
  const current = new Decimal(goal.currentAmount)
  const target = new Decimal(goal.targetAmount)
  if (current.gte(target)) return 'completed' as const
  if (goal.targetDate && goal.targetDate < now.toISOString().slice(0, 10)) return 'overdue' as const
  return goal.targetDate ? 'active' as const : 'no-deadline' as const
}

export function goalProgressPercent(goal: Goal) {
  return Math.min(100, new Decimal(goal.currentAmount).div(goal.targetAmount).mul(100).toDecimalPlaces(1).toNumber())
}
