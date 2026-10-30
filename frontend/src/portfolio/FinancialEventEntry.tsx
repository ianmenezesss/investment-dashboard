import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { FinancialEventInput, FinancialEventKind } from '../repositories/PrivateRepository'
import './portfolio.css'

const options: { kind: FinancialEventKind; label: string }[] = [
  { kind: 'CONTRIBUTION', label: 'Aporte externo' },
  { kind: 'WITHDRAWAL', label: 'Retirada externa' },
  { kind: 'DIVIDEND', label: 'Dividendo' },
  { kind: 'JCP', label: 'Juros sobre capital próprio (JCP)' },
  { kind: 'CORPORATE_ACTION', label: 'Observação de evento societário' },
]

function idempotencyKey() {
  if (!globalThis.crypto?.randomUUID) throw new Error('Este navegador não oferece geração segura de identificador. Atualize o navegador para registrar o evento.')
  return globalThis.crypto.randomUUID()
}

export function FinancialEventEntry({ repository }: { repository: { createFinancialEvent: (input: FinancialEventInput, key: string) => Promise<unknown> } }) {
  const client = useQueryClient()
  const [kind, setKind] = useState<FinancialEventKind>('CONTRIBUTION')
  const [submissionKey, setSubmissionKey] = useState<{ signature: string; key: string } | null>(null)
  const [keyError, setKeyError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: ({ input, key }: { input: FinancialEventInput; key: string }) => repository.createFinancialEvent(input, key),
    onSuccess: async () => {
      setSubmissionKey(null)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['unified-movements'] }),
        client.invalidateQueries({ queryKey: ['financial-event-summary'] }),
      ])
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const amount = (name: string) => String(form.get(name) ?? '').trim() || null
    const ticker = String(form.get('ticker') ?? '').trim().toUpperCase() || null
    const input: FinancialEventInput = {
      kind,
      event_date: String(form.get('event_date') ?? ''),
      ticker,
      cash_amount: amount('cash_amount'),
      gross_amount: amount('gross_amount'),
      tax_withheld: amount('tax_withheld'),
      source: String(form.get('source') ?? '').trim(),
      description: String(form.get('description') ?? '').trim() || null,
    }
    if (kind === 'CONTRIBUTION' || kind === 'WITHDRAWAL') {
      input.ticker = null
      input.gross_amount = null
      input.tax_withheld = null
      input.description = null
    } else if (kind === 'DIVIDEND' || kind === 'JCP') {
      input.description = null
    } else {
      input.cash_amount = null
      input.gross_amount = null
      input.tax_withheld = null
    }
    const formElement = event.currentTarget
    const signature = JSON.stringify(input)
    try {
      const key = submissionKey?.signature === signature ? submissionKey.key : idempotencyKey()
      setSubmissionKey({ signature, key })
      setKeyError(null)
      mutation.mutate({ input, key }, { onSuccess: () => formElement.reset() })
    } catch (error) {
      setKeyError(error instanceof Error ? error.message : 'Não foi possível gerar uma chave segura para o registro.')
    }
  }

  return <details className="panel financial-event-entry">
    <summary>Registrar aporte, provento ou evento observado</summary>
    <p>Use os valores e a data da fonte consultada. Proventos reinvestidos permanecem separados da compra; não registre o mesmo valor também como aporte externo.</p>
    <label>Tipo de registro<select aria-label="Tipo de registro financeiro" value={kind} onChange={event => { setKind(event.target.value as FinancialEventKind); mutation.reset() }}>{options.map(option => <option key={option.kind} value={option.kind}>{option.label}</option>)}</select></label>
    <form onSubmit={submit}>
      <label>Data<input name="event_date" type="date" required max={new Date().toLocaleDateString('en-CA')}/></label>
      {(kind === 'DIVIDEND' || kind === 'JCP' || kind === 'CORPORATE_ACTION') && <label>Ativo<input name="ticker" required pattern="[A-Z0-9]{4,20}" maxLength={20} aria-label="Ativo do evento"/></label>}
      {kind !== 'CORPORATE_ACTION' && <label>{kind === 'CONTRIBUTION' || kind === 'WITHDRAWAL' ? 'Valor em caixa (R$)' : 'Valor recebido registrado (R$)'}<input name="cash_amount" type="number" min="0.00000001" step="0.00000001" required/></label>}
      {(kind === 'DIVIDEND' || kind === 'JCP') && <>
        <label>Valor bruto (R$), se conhecido<input name="gross_amount" type="number" min="0.00000001" step="0.00000001"/></label>
        <label>Imposto retido (R$), se conhecido<input name="tax_withheld" type="number" min="0" step="0.00000001"/></label>
      </>}
      {kind === 'CORPORATE_ACTION' && <label>Descrição observada<textarea name="description" minLength={1} maxLength={1000} required/></label>}
      <label>Origem do registro<input name="source" minLength={1} maxLength={240} required placeholder="Extrato, informe ou documento consultado"/></label>
      {kind === 'CORPORATE_ACTION' && <p className="financial-event-note">Esta observação é apenas informativa e não altera quantidade, custo ou posição.</p>}
      {(keyError || mutation.isError) && <p role="alert">{keyError ?? (mutation.error instanceof Error ? mutation.error.message : 'Não foi possível registrar o evento.')}</p>}
      {mutation.isSuccess && <p role="status">Registro incluído no histórico.</p>}
      <button type="submit" disabled={mutation.isPending}>{mutation.isPending ? 'Salvando…' : 'Registrar'}</button>
    </form>
  </details>
}
