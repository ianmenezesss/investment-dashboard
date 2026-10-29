import { expect, test } from 'vitest'
import { getDisplayIdentity } from './displayIdentity'

test('prioriza nome dos metadados de sessão e deriva inicial Unicode', () => {
  expect(getDisplayIdentity({ email: 'ignored@example.test', user_metadata: { full_name: '  Ágata Souza ' } })).toEqual({ name: 'Ágata Souza', initial: 'Á' })
  expect(getDisplayIdentity({ email: 'ignored@example.test', user_metadata: { full_name: '', name: ' Bruno ' } })).toEqual({ name: 'Bruno', initial: 'B' })
})

test('usa prefixo do email e nome neutro quando não há metadados ou email válido', () => {
  expect(getDisplayIdentity({ email: 'marina.lima@example.test' })).toEqual({ name: 'marina.lima', initial: 'M' })
  expect(getDisplayIdentity({ email: '@example.test', user_metadata: { name: 42 } })).toEqual({ name: 'Investidor', initial: 'I' })
  expect(getDisplayIdentity(null)).toEqual({ name: 'Investidor', initial: 'I' })
})
