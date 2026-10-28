import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from '../components/ui/button'
import { marketMoney } from '../components/market-format'
import { financialToday, dayLabel, positive } from './format'
import type { Cdb, CdbDetail } from './types'

export type WriteMode = 'create' | 'application' | 'redemption'
export type DialogMode = WriteMode | 'choose' | null
const titles = { choose: 'Nova operação de renda fixa', create: 'Cadastrar CDB', application: 'Registrar aplicação', redemption: 'Registrar resgate de principal' }

function LedgerForm({ mode, detail, busy, onSave }: { mode: WriteMode; detail?: CdbDetail; busy: boolean; onSave: (mode: WriteMode, data: FormData) => void }) {
  const [remuneration, setRemuneration] = useState('CDI')
  const available = detail?.lots.filter(lot => positive(lot.principal_balance)) ?? []
  const [lotId, setLotId] = useState(String(available[0]?.id ?? ''))
  const [principal, setPrincipal] = useState('')
  const lot = available.find(item => String(item.id) === lotId)
  const [applicationDate, setApplicationDate] = useState(financialToday())
  return <form onSubmit={event => { event.preventDefault(); onSave(mode, new FormData(event.currentTarget)) }}>
    <fieldset disabled={busy} className="fi-form-fields">
      {mode === 'create' ? <>
        <label>Instituição emissora<input name="issuer" required maxLength={160}/></label>
        <label>Nome do produto<input name="product_name" required maxLength={160}/></label>
        <label>Remuneração<select name="remuneration" value={remuneration} onChange={event => setRemuneration(event.target.value)}><option value="CDI">Percentual do CDI</option><option value="FIXED">Prefixado</option></select></label>
        <label>{remuneration === 'CDI' ? 'Percentual do CDI (%)' : 'Taxa prefixada (% ao ano)'}<input name="contracted_rate" type="number" min="0.00000001" max="9999.99999999" step="0.00000001" required placeholder={remuneration === 'CDI' ? '110' : '12.5'}/></label>
        <label>Data da primeira aplicação<input name="application_date" type="date" required max={financialToday()} value={applicationDate} onChange={event => setApplicationDate(event.target.value)}/></label>
        <label>Vencimento<input name="maturity_date" type="date" required min={applicationDate}/></label>
        <p className="fi-full">Cadastrar o contrato não movimenta dinheiro. Registre a primeira aplicação depois, na data informada. Termos e movimentos não podem ser editados ou excluídos.</p>
      </> : <>
        {mode === 'redemption' && <label className="fi-full">Lote de origem<select name="lot_id" value={lotId} required onChange={event => { setLotId(event.target.value); setPrincipal('') }}>
          <option value="" disabled>Escolha um lote com principal</option>{available.map(item => <option key={item.id} value={item.id}>Lote {item.id} · {dayLabel(item.application_date)} · {marketMoney(item.principal_balance)}</option>)}
        </select></label>}
        <label>Data<input name="date" type="date" required max={mode === 'application' && detail ? [financialToday(), detail.maturity_date].sort()[0] : financialToday()}
          min={mode === 'redemption' ? lot?.application_date : detail?.application_date}
          defaultValue={mode === 'application' && detail ? detail.lots.length === 0 ? detail.application_date : [financialToday(), detail.maturity_date].sort()[0] : financialToday()}/></label>
        <label>{mode === 'application' ? 'Principal da aplicação (R$)' : 'Principal amortizado (R$)'}<input name="principal_amount" type="number" min="0.00000001" step="0.00000001" required value={principal} onChange={event => setPrincipal(event.target.value)} max={mode === 'redemption' ? lot?.principal_balance : undefined}/></label>
        {mode === 'redemption' && <>
          <Button className="fi-full" variant="outline" disabled={!lot} onClick={() => setPrincipal(lot!.principal_balance)}>Resgatar todo o principal do lote</Button>
          <label className="fi-full">Caixa líquido recebido (R$, opcional)<input name="cash_received" type="number" min="0" step="0.00000001" aria-describedby="fi-cash-help"/></label>
          <p id="fi-cash-help" className="fi-full">Informe somente o valor efetivo do extrato, se conhecido. Ele pode diferir do principal amortizado. Deixar vazio significa não informado, nunca zero.</p>
        </>}
        <p className="fi-full">{mode === 'application' ? 'Cada aplicação cria um novo lote. A primeira deve coincidir com a data do contrato.' : 'O resgate reduz o principal do lote escolhido. Não calcula nem registra impostos realizados.'} Registre as datas em ordem por CDB; movimentos são imutáveis.</p>
      </>}
      <Button type="submit" className="fi-full" disabled={mode === 'redemption' && !lot}>{busy ? 'Registrando…' : titles[mode]}</Button>
    </fieldset>
  </form>
}

export function FixedIncomeDialog({ mode, setMode, cdbs, selected, select, detail, busy, error, onSave, returnFocus }: {
  mode: DialogMode; setMode: (mode: DialogMode) => void; cdbs: Cdb[]; selected: number | null; select: (id: number) => void
  detail?: CdbDetail; busy: boolean; error: string; onSave: (mode: WriteMode, data: FormData) => void; returnFocus: HTMLElement | null
}) {
  return <Dialog.Root open={mode !== null} onOpenChange={open => { if (!open && !busy) setMode(null) }}><Dialog.Portal><Dialog.Overlay className="overlay fi-overlay"/>
    <Dialog.Content className="modal fi-modal" onCloseAutoFocus={event => { event.preventDefault(); returnFocus?.focus() }} onEscapeKeyDown={event => { if (busy) event.preventDefault() }} onPointerDownOutside={event => { if (busy) event.preventDefault() }}>
      <Dialog.Title>{mode ? titles[mode] : ''}</Dialog.Title><Dialog.Description>Registros reais da sua carteira privada. Valores em reais.</Dialog.Description>
      <button className="close" aria-label="Fechar formulário de renda fixa" disabled={busy} onClick={() => setMode(null)}><X size={20}/></button>
      {error && <p role="alert" className="error">{error}</p>}
      {mode === 'choose' ? <div className="fi-chooser">
        <Button onClick={() => setMode('create')}>Cadastrar novo CDB</Button>
        <label>CDB para movimentar<select value={selected ?? ''} onChange={event => select(Number(event.target.value))}><option value="" disabled>Escolha um investimento</option>{detail && !cdbs.some(cdb => cdb.id === detail.id) && <option value={detail.id}>{detail.product_name}</option>}{cdbs.map(cdb => <option key={cdb.id} value={cdb.id}>{cdb.product_name} · {cdb.issuer}</option>)}</select></label>
        <Button disabled={!detail} onClick={() => setMode('application')}>Nova aplicação por lote</Button>
        <Button variant="outline" disabled={!detail?.lots.some(lot => positive(lot.principal_balance))} onClick={() => setMode('redemption')}>Resgatar principal</Button>
      </div> : mode && (mode !== 'create' && !detail ? <p role="status">Carregando o CDB selecionado…</p> : <LedgerForm key={`${mode}-${detail?.id ?? 'new'}`} mode={mode} detail={detail} busy={busy} onSave={onSave}/>)}
    </Dialog.Content></Dialog.Portal></Dialog.Root>
}
