import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import Decimal from 'decimal.js'
import { Button } from '../components/ui/button'
import { marketMoney } from '../components/market-format'
import { financialToday, dayLabel } from './format'
import type { CdbDetail, ObservedPositionInput } from './types'

const Money = Decimal.clone({ precision: 64 })
export function parseObservedBRL(raw: string): string | null {
  if (!raw.trim()) return null
  if (!/^-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$/.test(raw)) throw new Error('Use valores em reais com vírgula e até duas casas decimais, por exemplo 1.000,00.')
  const value = new Money(raw.replaceAll('.', '').replace(',', '.'))
  if (value.abs().gt('999999999999.99')) throw new Error('O valor ultrapassa o limite permitido.')
  return value.toFixed(2)
}
function CurrencyField({ name, label, required = false, signed = false, initial }: { name: string; label: string; required?: boolean; signed?: boolean; initial?: string|null }) {
  const [value,setValue] = useState(initial ? marketMoney(initial).replace('R$ ', '') : '')
  return <label>{label}{!required && ' (opcional)'}<span className="fi-currency"><span>R$</span><input name={name} inputMode="decimal" required={required} value={value} placeholder={required ? '0,00' : 'Não informado'} onChange={event => setValue(event.target.value)} onBlur={() => { try { const parsed = parseObservedBRL(value); if (parsed !== null && (signed || new Money(parsed).gte(0))) setValue(marketMoney(parsed).replace('R$ ', '')) } catch { /* retain input for correction, never coerce to zero */ } }}/></span></label>
}

export function ManualPositionDialog({ detail, opening, busy, error, close, save, returnFocus }: { detail: CdbDetail; opening: boolean; busy: boolean; error: string; close: () => void; save: (data: ObservedPositionInput) => void; returnFocus: HTMLElement | null }) {
  const [taxMode,setTaxMode] = useState('combined'), [reason,setReason] = useState<ObservedPositionInput['reason']>('POSITION')
  const [review,setReview] = useState<ObservedPositionInput | null>(null), [localError,setLocalError] = useState('')
  const [draft,setDraft] = useState<ObservedPositionInput|null>(null)
  return <Dialog.Root open onOpenChange={open => { if(!open&&!busy) close() }}><Dialog.Portal><Dialog.Overlay className="overlay fi-overlay"/><Dialog.Content className="modal fi-modal" onCloseAutoFocus={event => {event.preventDefault();returnFocus?.focus()}} onEscapeKeyDown={event => {if(busy)event.preventDefault()}} onPointerDownOutside={event => {if(busy)event.preventDefault()}}>
    <Dialog.Title>{opening ? 'Iniciar acompanhamento com saldo atual' : 'Registrar nova posição observada'}</Dialog.Title><Dialog.Description>Informe a posição do CDB inteiro na data escolhida. Não é aplicação, não cria lotes nem reconstrói o passado.</Dialog.Description>
    <button className="close" disabled={busy} aria-label="Fechar posição manual" onClick={close}>×</button>
    {(error||localError) && <p className="error" role="alert">{localError||error}</p>}
    {!review ? <form onSubmit={event => {event.preventDefault();setLocalError('');try {
      const form=new FormData(event.currentTarget), text=(name:string)=>String(form.get(name)??''), money=(name:string)=>parseObservedBRL(text(name))
      const input:ObservedPositionInput={as_of:text('as_of'),gross_value:money('gross_value')!,net_value:money('net_value')!,ir_estimate:money('ir_estimate'),iof_estimate:money('iof_estimate'),taxes_combined:money('taxes_combined'),reported_gain:money('reported_gain'),confirmed_principal:money('confirmed_principal'),source:text('source').trim(),notes:text('notes').trim()||null,reason,cash_received:money('cash_received')}
      if(input.gross_value===null||input.net_value===null||!input.source)throw new Error('Preencha data-base, fonte, patrimônio bruto e líquido.')
      for(const key of ['gross_value','net_value','ir_estimate','iof_estimate','taxes_combined','confirmed_principal','cash_received'] as const)if(input[key]!==null&&new Money(input[key]!).lt(0))throw new Error('Patrimônio, principal e tributos não podem ser negativos.')
      const difference=new Money(input.gross_value).minus(input.net_value)
      if(difference.lt(0))throw new Error('O líquido não pode superar o patrimônio bruto.')
      if(input.taxes_combined!==null&&!difference.eq(input.taxes_combined))throw new Error('Bruto menos tributos combinados deve corresponder ao líquido.')
      const known=new Money(input.ir_estimate??0).plus(input.iof_estimate??0)
      if(known.gt(difference)||input.ir_estimate!==null&&input.iof_estimate!==null&&!known.eq(difference))throw new Error('Confira o IR e o IOF: os valores não correspondem ao bruto e líquido.')
      setDraft(input);setReview(input)
    }catch(cause){setLocalError((cause as Error).message)}}}>
      <fieldset className="fi-form-fields" disabled={busy}>
        <label>Data-base<input name="as_of" type="date" required min={detail.latest_observation?.as_of??detail.application_date} max={financialToday()} defaultValue={draft?.as_of??financialToday()}/></label>
        <label>Fonte da informação<input name="source" required maxLength={160} defaultValue={draft?.source} placeholder="Aplicativo ou extrato da instituição"/></label>
        <CurrencyField name="gross_value" label="Patrimônio bruto observado" initial={draft?.gross_value} required/><CurrencyField name="net_value" label="Disponível líquido para resgate" initial={draft?.net_value} required/>
        <label className="fi-full">Como os tributos são informados?<select name="tax_mode" value={taxMode} onChange={event=>setTaxMode(event.target.value)}><option value="combined">Tributos combinados</option><option value="separate">IR e IOF discriminados</option><option value="unknown">Não informados</option></select></label>
        {taxMode==='combined'&&<CurrencyField name="taxes_combined" label="Tributos combinados" initial={draft?.taxes_combined}/>}{taxMode==='separate'&&<><CurrencyField name="ir_estimate" label="IR informado" initial={draft?.ir_estimate}/><CurrencyField name="iof_estimate" label="IOF informado" initial={draft?.iof_estimate}/></>}
        <CurrencyField name="reported_gain" label="Ganhos/perdas apresentados pela instituição" initial={draft?.reported_gain} signed/><CurrencyField name="confirmed_principal" label="Principal remanescente confirmado" initial={draft?.confirmed_principal}/>
        <p className="fi-full">Se não conhece o principal, deixe em branco. Não o deduzimos do patrimônio ou dos ganhos. Tributos desconhecidos também permanecem não informados.</p>
        {!opening&&<label className="fi-full">Motivo da observação<select name="reason" value={reason} onChange={event=>setReason(event.target.value as typeof reason)}><option value="POSITION">Conferência manual de posição</option><option value="AFTER_CONSOLIDATED_REDEMPTION">Conciliação após resgate do capital consolidado</option></select></label>}
        {reason==='AFTER_CONSOLIDATED_REDEMPTION'&&<><CurrencyField name="cash_received" label="Caixa efetivamente recebido no resgate" initial={draft?.cash_received}/><p className="fi-full">Informe a nova posição inteira após o resgate. Não criamos amortização, principal ou imposto presumidos.</p></>}
        <label className="fi-full">Observações (opcional)<textarea name="notes" maxLength={1000} defaultValue={draft?.notes??''} placeholder="Contexto da posição, sem dados bancários ou do titular"/></label>
        <Button type="submit" className="fi-full">Revisar posição</Button>
      </fieldset>
    </form> : <div className="fi-review"><h3>Confirme antes de salvar</h3><p>{detail.product_name} · {dayLabel(review.as_of)} · {review.source}</p>
      <dl>{[['Patrimônio bruto',review.gross_value],['Disponível líquido',review.net_value],['Tributos combinados',review.taxes_combined],['IR informado',review.ir_estimate],['IOF informado',review.iof_estimate],['Ganhos/perdas informados',review.reported_gain],['Principal confirmado',review.confirmed_principal]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value===null?'Não informado':marketMoney(value)}</dd></div>)}</dl>
      {review.reason==='AFTER_CONSOLIDATED_REDEMPTION'&&<p>Conciliação após resgate do capital consolidado · Caixa recebido: {review.cash_received===null?'Não informado':marketMoney(review.cash_received)}. Principal e resultado realizado não são deduzidos desse caixa.</p>}
      {review.notes&&<p>Observações: {review.notes}</p>}
      <p className="fi-notice">Registro manual imutável. Não substitui o histórico real, não cria aplicações e não autoriza cálculo retroativo de CDI ou impostos.</p>
      <div className="fi-actions"><Button variant="outline" disabled={busy} onClick={()=>{setReview(null);setLocalError('')}}>Voltar ao formulário</Button><Button disabled={busy} onClick={()=>save(review)}>{busy?'Salvando posição…':'Confirmar e salvar posição'}</Button></div>
    </div>}
  </Dialog.Content></Dialog.Portal></Dialog.Root>
}
