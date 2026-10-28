import { useEffect, useRef, useState, type FormEvent } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { ApiError } from '../api'
import { Button } from '../components/ui/button'
import { marketMoney } from '../components/market-format'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import type { CdbApplicationRevisionInput, CdbApplicationRevisionPreview, CdbMovement } from './types'
import { dayLabel } from './format'

export type RevisionKind = 'REPLACE' | 'VOID'

function newIdempotencyKey() {
  if (!globalThis.crypto?.getRandomValues) throw new Error('Este navegador não oferece geração segura de identificadores. Atualize o navegador e tente novamente.')
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function errorMessage(error: unknown, phase: 'preview' | 'save') {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'O contrato ou a aplicação não foi encontrado. Atualize a carteira e tente novamente.'
    if (error.status === 409) return `A revisão entrou em conflito ou está desatualizada. Feche e reabra o formulário para carregar a sequência atual. ${error.message}`
    if (error.status === 422) return `Operação inválida: ${error.message}`
    if (error.status === 401 || error.status === 403) return error.message
    if (error.status >= 500 && phase === 'save') return 'Não foi possível confirmar se a revisão foi gravada. Tente novamente sem alterar o formulário; a mesma chave de idempotência será reutilizada.'
  }
  if (error instanceof TypeError && phase === 'save') return 'Falha de rede. O resultado pode não estar confirmado. Tente novamente sem alterar o formulário; a mesma chave de idempotência será reutilizada.'
  return error instanceof Error ? error.message : 'Não foi possível concluir esta operação.'
}

export function ApplicationRevisionDialog({ investmentId, movement, kind, repository, onClose, onSuccess, onAuthError, onConflict, returnFocus }: {
  investmentId: number; movement: CdbMovement; kind: RevisionKind; repository: PrivateRepository
  onClose: () => void; onSuccess: () => void; onAuthError: (error: ApiError) => void
  onConflict: () => void; returnFocus: HTMLElement | null
}) {
  const [amount, setAmount] = useState(movement.principal_amount)
  const [date, setDate] = useState(movement.date)
  const [reason, setReason] = useState('')
  const [expectedRevision, setExpectedRevision] = useState<number | null>(null)
  const [loadingRevision, setLoadingRevision] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<CdbApplicationRevisionPreview | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const active = useRef(true)
  const inFlight = useRef(false)
  const intentKey = useRef<{ signature: string; key: string } | null>(null)
  const signature = JSON.stringify([kind, expectedRevision, amount, date, reason])

  useEffect(() => {
    active.current = true
    const controller = new AbortController()
    void repository.latestCdbApplicationRevision(investmentId, movement.id, controller.signal)
      .then(revision => { if (active.current) setExpectedRevision(revision) })
      .catch(cause => {
        if (!active.current) return
        if (cause instanceof ApiError && [401, 403].includes(cause.status)) onAuthError(cause)
        else setError(errorMessage(cause, 'preview'))
      })
      .finally(() => { if (active.current) setLoadingRevision(false) })
    return () => { active.current = false; controller.abort() }
  }, [investmentId, movement.id, repository, onAuthError])

  function keyForIntent() {
    if (!intentKey.current || intentKey.current.signature !== signature) intentKey.current = { signature, key: newIdempotencyKey() }
    return intentKey.current.key
  }
  function change<T>(setter: (value: T) => void, value: T) {
    setter(value); setPreview(null); setConfirmed(false); setError('')
  }
  function input(): CdbApplicationRevisionInput {
    if (expectedRevision === null) throw new Error('A sequência atual ainda não foi carregada.')
    if (!reason.trim()) throw new Error('Informe o motivo da revisão.')
    if (kind === 'REPLACE') {
      if (!amount.trim() || !date) throw new Error('Informe o principal total e a data efetiva.')
      return { kind, expected_revision: expectedRevision, reason: reason.trim(), replacement_amount: amount, replacement_date: date }
    }
    return { kind, expected_revision: expectedRevision, reason: reason.trim() }
  }
  async function inspectImpact(event: FormEvent) {
    event.preventDefault()
    if (inFlight.current || loadingRevision || expectedRevision === null) return
    inFlight.current = true; setBusy(true); setError('')
    try {
      const result = await repository.previewCdbApplicationRevision(investmentId, movement.id, input(), keyForIntent())
      if (!active.current) return
      setPreview(result); setConfirmed(false)
    } catch (cause) {
      if (!active.current) return
      if (cause instanceof ApiError && [401, 403].includes(cause.status)) onAuthError(cause)
      else { setError(errorMessage(cause, 'preview')); if (cause instanceof ApiError && cause.status === 409) onConflict() }
    } finally { inFlight.current = false; if (active.current) setBusy(false) }
  }
  async function confirmRevision() {
    if (inFlight.current || !preview || !confirmed || expectedRevision === null) return
    inFlight.current = true; setBusy(true); setError('')
    try {
      await repository.createCdbApplicationRevision(investmentId, movement.id, input(), keyForIntent())
      if (!active.current) return
      onSuccess()
    } catch (cause) {
      if (!active.current) return
      if (cause instanceof ApiError && [401, 403].includes(cause.status)) onAuthError(cause)
      else { setError(errorMessage(cause, 'save')); if (cause instanceof ApiError && cause.status === 409) onConflict() }
    } finally { inFlight.current = false; if (active.current) setBusy(false) }
  }

  const title = kind === 'REPLACE' ? 'Corrigir aplicação' : 'Anular aplicação'
  return <Dialog.Root open onOpenChange={open => { if (!open && !busy) onClose() }}>
    <Dialog.Portal><Dialog.Overlay className="overlay fi-overlay"/>
      <Dialog.Content className="modal fi-modal fi-revision-modal" onCloseAutoFocus={event => { event.preventDefault(); if (returnFocus?.isConnected) returnFocus.focus(); else document.querySelector<HTMLElement>('.fi-detail h2')?.focus() }} onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => { if (busy) event.preventDefault() }}>
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description>O lançamento original permanece preservado. A revisão cria um evento de auditoria e atualiza somente a projeção efetiva.</Dialog.Description>
        <button className="close" aria-label="Fechar revisão" disabled={busy} onClick={onClose}><X size={20}/></button>
        {error && <p role="alert" className="error">{error}</p>}
        {loadingRevision ? <p role="status">Carregando sequência de revisões…</p> : expectedRevision === null ? <p role="alert">Não foi possível carregar a sequência. Feche e tente abrir novamente.</p> : <form onSubmit={event => { void inspectImpact(event) }}>
          <fieldset className="fi-form-fields" disabled={busy}>
            <p className="fi-full">Aplicação #{movement.id} · Lote #{movement.lot_id} · Atual: {marketMoney(movement.principal_amount)} em {dayLabel(movement.date)} · Próxima sequência: {expectedRevision + 1}</p>
            {kind === 'REPLACE' && <>
              <label>Principal total corrigido (R$)<input name="replacement_amount" type="number" min="0.00000001" step="0.00000001" required value={amount} onChange={event => change(setAmount, event.target.value)}/></label>
              <label>Data efetiva<input name="replacement_date" type="date" required value={date} onChange={event => change(setDate, event.target.value)}/></label>
            </>}
            {kind === 'VOID' && <p className="fi-full fi-notice">A anulação remove a aplicação da projeção efetiva quando validada. É uma anulação contábil: não registra caixa e não cria um resgate fictício. A API pode bloquear a operação se houver resgates ou outras dependências incompatíveis.</p>}
            <label className="fi-full">Motivo obrigatório<textarea name="reason" required maxLength={1000} value={reason} onChange={event => change(setReason, event.target.value)}/></label>
            <Button type="submit" className="fi-full" disabled={busy || !reason.trim() || !!preview}>{busy ? 'Verificando impacto…' : 'Ver impacto antes de confirmar'}</Button>
          </fieldset>
        </form>}
        {preview && <section className="fi-review" aria-live="polite" aria-label="Prévia do impacto">
          <h3>Impacto no principal registrado</h3>
          <dl><div><dt>Saldo do lote #{preview.lot_id} antes</dt><dd>{marketMoney(preview.principal_before)}</dd></div>
            <div><dt>Saldo do lote após a revisão</dt><dd>{marketMoney(preview.principal_after)}</dd></div>
            {kind === 'REPLACE' && <div><dt>Novo registro efetivo</dt><dd>{marketMoney(preview.amount ?? amount)} · {dayLabel(preview.effective_date ?? date)}</dd></div>}
          </dl>
          <p>A prévia não estima rendimento, impostos nem caixa de resgate. A confirmação será revalidada pelo servidor.</p>
          {kind === 'VOID' && <p className="fi-notice">Esta ação é contábil. Nenhum valor será registrado como recebido e o movimento original não será apagado.</p>}
          <label className="fi-confirm"><input type="checkbox" disabled={busy} checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/>
            {kind === 'REPLACE' ? 'Confirmo substituir os valores efetivos desta aplicação, mantendo o lançamento original no histórico.' : 'Confirmo anular contabilmente esta aplicação; entendo que não é um resgate e não cria caixa recebido.'}
          </label>
          <Button disabled={busy || !confirmed} onClick={() => { void confirmRevision() }}>{busy ? 'Registrando revisão…' : kind === 'REPLACE' ? 'Confirmar correção' : 'Confirmar anulação'}</Button>
        </section>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
