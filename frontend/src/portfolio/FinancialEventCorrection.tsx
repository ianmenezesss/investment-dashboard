import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FinancialEventInput, FinancialEventKind, PrivateRepository, UnifiedMovement } from '../repositories/PrivateRepository'

const eventKinds: { value: FinancialEventKind; label: string }[] = [
  { value: 'CONTRIBUTION', label: 'Aporte externo' },
  { value: 'WITHDRAWAL', label: 'Retirada externa' },
  { value: 'DIVIDEND', label: 'Dividendo' },
  { value: 'JCP', label: 'JCP' },
  { value: 'CORPORATE_ACTION', label: 'Observação societária' },
]

function newIdempotencyKey() {
  if (!globalThis.crypto?.randomUUID) throw new Error('Este navegador não oferece geração segura de identificador. Atualize o navegador para revisar o evento.')
  return globalThis.crypto.randomUUID()
}

function field(form: FormData, name: string) {
  return String(form.get(name) ?? '').trim() || null
}

export function FinancialEventCorrection({ repository, identity, row, eventId }: {
  repository: Pick<PrivateRepository, 'reviseFinancialEvent' | 'financialEventRevisions'>
  identity: string
  row: UnifiedMovement
  eventId: number
}) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [replacementKind, setReplacementKind] = useState<FinancialEventKind>(row.operation as FinancialEventKind)
  const [reason, setReason] = useState('')
  const [confirmVoid, setConfirmVoid] = useState(false)
  const [submissionKey, setSubmissionKey] = useState<{ signature: string; key: string } | null>(null)
  const [keyError, setKeyError] = useState<string | null>(null)
  const revisions = useQuery({
    queryKey: ['financial-event-revisions', identity, eventId],
    queryFn: ({ signal }) => repository.financialEventRevisions(eventId, signal),
    enabled: open,
    retry: false,
  })
  const mutation = useMutation({
    mutationFn: ({ input, key }: { input: { kind: 'REPLACE' | 'VOID'; expected_revision: number; reason: string; replacement?: FinancialEventInput }; key: string }) =>
      repository.reviseFinancialEvent(eventId, input, key),
    onSuccess: async () => {
      setConfirmVoid(false)
      setReason('')
      setSubmissionKey(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['unified-movements'] }),
        client.invalidateQueries({ queryKey: ['financial-event-summary'] }),
        client.invalidateQueries({ queryKey: ['financial-event-revisions', identity, eventId] }),
      ])
    },
  })

  function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const replacement: FinancialEventInput = {
      kind: replacementKind,
      event_date: String(form.get('event_date') ?? ''),
      ticker: field(form, 'ticker'),
      cash_amount: field(form, 'cash_amount'),
      gross_amount: field(form, 'gross_amount'),
      tax_withheld: field(form, 'tax_withheld'),
      source: String(form.get('source') ?? '').trim(),
      description: field(form, 'description'),
    }
    if (replacementKind === 'CONTRIBUTION' || replacementKind === 'WITHDRAWAL') {
      replacement.ticker = null
      replacement.gross_amount = null
      replacement.tax_withheld = null
      replacement.description = null
    } else if (replacementKind === 'DIVIDEND' || replacementKind === 'JCP') {
      replacement.description = null
    } else {
      replacement.cash_amount = null
      replacement.gross_amount = null
      replacement.tax_withheld = null
    }
    submitRevision({ kind: 'REPLACE', expected_revision: row.revision ?? 0, reason, replacement })
  }

  function voidEvent() {
    submitRevision({ kind: 'VOID', expected_revision: row.revision ?? 0, reason })
  }

  function submitRevision(input: { kind: 'REPLACE' | 'VOID'; expected_revision: number; reason: string; replacement?: FinancialEventInput }) {
    const signature = JSON.stringify(input)
    try {
      const key = submissionKey?.signature === signature ? submissionKey.key : newIdempotencyKey()
      setSubmissionKey({ signature, key })
      setKeyError(null)
      mutation.mutate({ input, key })
    } catch (error) {
      setKeyError(error instanceof Error ? error.message : 'Não foi possível gerar uma chave segura para a revisão.')
    }
  }

  return <details className="financial-event-correction" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary aria-label={`Corrigir ou anular ${row.asset} ${row.operation}`}>Corrigir / anular</summary>
    {open && <section className="financial-event-revisions" aria-label="Revisões deste evento">
      <h4>Histórico de revisões</h4>
      {revisions.isPending ? <p role="status">Carregando revisões…</p> : revisions.isError ? <p role="alert">Não foi possível carregar as revisões.</p> : revisions.data?.length ? <ol>
        {revisions.data.map(revision => <li key={revision.id}>Rev. {revision.revision} · {revision.kind === 'VOID' ? 'anulação' : 'substituição'} · {revision.reason}</li>)}
      </ol> : <p>Este registro ainda não possui revisões.</p>}
    </section>}
    <form onSubmit={replace}>
      <label>Tipo<select aria-label={`Tipo corrigido ${row.asset}`} value={replacementKind} onChange={event => setReplacementKind(event.target.value as FinancialEventKind)}>{eventKinds.map(item => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
      <label>Data<input name="event_date" type="date" defaultValue={row.date} required max={new Date().toLocaleDateString('en-CA')}/></label>
      {(replacementKind === 'DIVIDEND' || replacementKind === 'JCP' || replacementKind === 'CORPORATE_ACTION') && <label>Ativo<input name="ticker" defaultValue={row.asset === 'Carteira' ? '' : row.asset} required pattern="[A-Z0-9]{4,20}" maxLength={20}/></label>}
      {replacementKind !== 'CORPORATE_ACTION' && <label>Valor em caixa (R$)<input name="cash_amount" type="number" min="0.00000001" step="0.00000001" defaultValue={row.financial_value ?? ''} required/></label>}
      {(replacementKind === 'DIVIDEND' || replacementKind === 'JCP') && <>
        <label>Valor bruto (R$), se conhecido<input name="gross_amount" type="number" min="0.00000001" step="0.00000001" defaultValue={row.gross_amount ?? ''}/></label>
        <label>Imposto retido (R$), se conhecido<input name="tax_withheld" type="number" min="0" step="0.00000001" defaultValue={row.tax_withheld ?? ''}/></label>
      </>}
      {replacementKind === 'CORPORATE_ACTION' && <label>Descrição observada<textarea name="description" defaultValue={row.description ?? ''} minLength={1} maxLength={1000} required/></label>}
      <label>Origem<input name="source" defaultValue={row.source ?? ''} minLength={1} maxLength={240} required/></label>
      <label>Motivo da revisão<textarea value={reason} onChange={event => { setReason(event.target.value); setConfirmVoid(false) }} minLength={1} maxLength={1000} required/></label>
      {(keyError || mutation.isError) && <p role="alert">{keyError ?? (mutation.error instanceof Error ? mutation.error.message : 'Não foi possível revisar o evento.')}</p>}
      {mutation.isSuccess && <p role="status">Revisão registrada no histórico append-only.</p>}
      <div className="financial-event-correction-actions">
        <button type="submit" disabled={mutation.isPending || !reason.trim()}>Salvar substituição</button>
        {!confirmVoid ? <button type="button" className="secondary" disabled={mutation.isPending || !reason.trim()} onClick={() => setConfirmVoid(true)}>Anular lançamento…</button> : <div className="financial-event-void-confirmation" role="group" aria-label="Confirmação da anulação">
          <p role="status">A anulação é permanente no histórico auditável. Confirmar?</p>
          <button type="button" disabled={mutation.isPending} onClick={voidEvent}>Confirmar anulação</button>
          <button type="button" className="secondary" onClick={() => setConfirmVoid(false)}>Cancelar</button>
        </div>}
      </div>
    </form>
  </details>
}
