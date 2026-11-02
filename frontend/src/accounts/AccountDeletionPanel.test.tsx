import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, test, vi } from 'vitest'
import { AccountDeletionPanel } from './AccountDeletionPanel'
import { goalsStorageKey } from '../goals/goalStorage'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))
vi.mock('../api', () => ({ request: (...args: unknown[]) => requestMock(...args) }))

let host: HTMLDivElement
let root: Root

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  localStorage.clear()
  vi.clearAllMocks()
})

function setValue(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

test('exclusão envia somente confirmação explícita com um token reautenticado e limpa metas locais', async () => {
  const identity = '22222222-2222-4222-8222-222222222222'
  localStorage.setItem(goalsStorageKey(identity), 'fictional-private-goal')
  const reauthenticate = vi.fn().mockResolvedValue({ access_token: 'fresh-test-token' })
  const onDeleted = vi.fn().mockResolvedValue(undefined)
  requestMock.mockResolvedValue({ status: 'deleted' })
  host = document.createElement('div'); document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<AccountDeletionPanel identity={identity} reauthenticate={reauthenticate} onDeleted={onDeleted}/>))

  const inputs = host.querySelectorAll('input')
  await act(async () => {
    setValue(inputs[0], 'fictional-password')
    setValue(inputs[1], 'EXCLUIR MINHA CONTA')
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))

  expect(reauthenticate).toHaveBeenCalledWith('fictional-password')
  expect(requestMock).toHaveBeenCalledWith('account/delete', 'fresh-test-token', {
    method: 'POST', body: JSON.stringify({ confirmation: 'EXCLUIR MINHA CONTA' }),
  })
  expect(JSON.stringify(requestMock.mock.calls)).not.toContain(identity)
  expect(JSON.stringify(requestMock.mock.calls)).not.toContain('fictional-password')
  expect(localStorage.getItem(goalsStorageKey(identity))).toBeNull()
  expect(onDeleted).toHaveBeenCalledWith(true)
})

test('falha na reautenticação não inicia exclusão', async () => {
  const reauthenticate = vi.fn().mockRejectedValue(new Error('Senha incorreta'))
  host = document.createElement('div'); document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<AccountDeletionPanel identity="owner" reauthenticate={reauthenticate} onDeleted={vi.fn()}/>))
  const inputs = host.querySelectorAll('input')
  await act(async () => {
    setValue(inputs[0], 'wrong-password')
    setValue(inputs[1], 'EXCLUIR MINHA CONTA')
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(host.textContent).toContain('Senha incorreta')
  expect(requestMock).not.toHaveBeenCalled()
})
