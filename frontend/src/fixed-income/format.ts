import Decimal from 'decimal.js'
import type { CdbMovement, Cdb } from './types'
const Exact = Decimal.clone({ precision: 64 })
export const financialToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date())
export const dayLabel = (value: string) => new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' }).format(new Date(value + 'T12:00:00Z'))
export const timeLabel = (value: string) => new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) + ' (Brasília)'
export const positive = (value: string) => { try { return new Exact(value).isFinite() && new Exact(value).gt(0) } catch { return false } }
export const exceeds = (value: string, maximum: string) => { try { return new Exact(value).gt(maximum) } catch { return true } }
export const totalApplications = (rows: CdbMovement[]) => rows.filter(row => row.kind === 'APPLICATION').reduce((sum, row) => sum.plus(row.principal_amount), new Exact(0)).toFixed()
export const contractLabel = (cdb: Cdb) => `${new Exact(cdb.contracted_rate).toFixed().replace('.', ',')}% ${cdb.remuneration === 'CDI' ? 'do CDI' : 'a.a. prefixado'}`
