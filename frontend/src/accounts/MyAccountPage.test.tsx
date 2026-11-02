import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { MyAccountPage } from './MyAccountPage'

vi.mock('./InvitationAdmin', () => ({ InvitationAdmin: () => <div data-testid="invitation-admin">Painel de convites</div> }))

let host: HTMLDivElement
let root: Root
function mount(isAdmin: boolean) {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host)
  return act(async () => root.render(<MemoryRouter><MyAccountPage name="Ana Souza" email="ana@example.test" isAdmin={isAdmin} status="Ativa" accessStatus="active" activatedAt="2026-11-02T12:00:00Z" expiresAt="2026-11-09T12:00:00Z" identity="user-ana" token="verified-session-token" reauthenticate={async () => ({ access_token: 'fresh-token' })} onDeleted={async () => {}}/></MemoryRouter>))
}
afterEach(async () => { if (root) await act(async () => root.unmount()); host?.remove() })

test('mostra identidade da sessão, volta para a carteira e reserva convites e zona de perigo para a conta', async () => {
  await mount(true)
  expect(host.textContent).toContain('Ana Souza')
  expect(host.textContent).toContain('ana@example.test')
  expect(host.textContent).toContain('Administrador')
  expect(host.textContent).toContain('Teste de 7 dias')
  expect(host.textContent).toContain('Ativada em')
  expect(host.textContent).toContain('Expira em')
  expect(host.querySelector('a[href="/"]')?.textContent).toContain('Voltar à carteira')
  expect(host.querySelector('[data-testid="invitation-admin"]')).not.toBeNull()
  const danger = host.querySelector('#account-danger-title')?.closest('section')
  expect(danger?.textContent).toContain('Zona de perigo')
  expect(danger?.textContent).toContain('Excluir minha conta')
})

test('usuário comum não recebe controles de administração e mantém as proteções de exclusão', async () => {
  await mount(false)
  expect(host.textContent).toContain('Usuário')
  expect(host.textContent).toContain('Teste de 7 dias')
  expect(host.querySelector('[data-testid="invitation-admin"]')).toBeNull()
  expect(host.querySelector('#account-danger-title')?.closest('section')?.textContent).toContain('Zona de perigo')
  expect(host.textContent).toContain('Confirme sua senha')
  expect(host.textContent).toContain('EXCLUIR MINHA CONTA')
})
