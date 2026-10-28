import { marketMoney } from '../components/market-format'
import { FinancialHint } from '../components/FinancialHint'
import type { ObservedPosition } from './types'
import { dayLabel } from './format'

export function ObservedPositionSummary({ position }: { position: ObservedPosition }) {
  return <article className="panel fi-section fi-observed" aria-label="Posição informada pela instituição">
    <span className="tag">Posição informada manualmente</span><h3>Posição informada pela instituição <FinancialHint label="posição observada">Snapshot do CDB inteiro informado pelo usuário na data-base. Não é uma aplicação, não reconstrói o histórico de aquisição e não é somado aos lotes posteriores.</FinancialHint></h3>
    <p><span className="fi-value-origin fi-origin-user">Informado pelo usuário</span> Data-base {dayLabel(position.as_of)} · Fonte: {position.source}. É o saldo do CDB inteiro naquela data e não se atualiza automaticamente com novas operações.</p>
    <div className="fi-metrics">{[['Patrimônio bruto observado', position.gross_value], ['Disponível líquido observado', position.net_value], ['Ganhos/perdas informados', position.reported_gain]].map(([label,value]) => <article className="metric" key={label}><span>{label} <FinancialHint label={String(label)}>{label === 'Patrimônio bruto observado' ? 'Valor bruto declarado a partir da fonte e data-base informadas; não é calculado pelo ledger.' : label === 'Disponível líquido observado' ? 'Valor líquido declarado pelo usuário para a posição inteira, depois dos tributos que a fonte informou.' : 'Informação declarada separadamente pelo usuário. Não determina o principal confirmado nem lucro tributável.'}</FinancialHint></span><h2>{marketMoney(value)}</h2><small className="fi-value-origin fi-origin-user">Informado pelo usuário</small></article>)}</div>
    <div className="fi-notice">{position.taxes_combined !== null ? <>Tributos combinados informados: <strong>{marketMoney(position.taxes_combined)}</strong></> : <>IR informado: <strong>{marketMoney(position.ir_estimate)}</strong> · IOF informado: <strong>{marketMoney(position.iof_estimate)}</strong></>} <FinancialHint label="tributos informados">Valores preenchidos pelo usuário conforme a fonte. Podem estar ausentes ou ser estimativas da instituição; não são calculados nem confirmados pelo sistema.</FinancialHint>
      <p>{position.confirmed_principal === null ? 'Principal não informado.' : <>Principal confirmado nesta data: {marketMoney(position.confirmed_principal)}.</>} Ganhos/perdas são uma métrica independente; não definem principal nem lucro tributável.</p>
    </div>
    <p>Rentabilidade histórica indisponível. Esta posição não substitui o histórico de aquisição e não constitui base para CDI ou tributação retroativa.</p>
    <details><summary>Informações adicionais da posição</summary><p>Registrada em {position.created_at}. Origem: {position.kind === 'OPENING' ? 'Abertura de acompanhamento' : 'Nova observação, sem sobrescrever anteriores'}.</p>{position.notes && <p>Observações: {position.notes}</p>}{position.reason === 'AFTER_CONSOLIDATED_REDEMPTION' && <p>Conciliação após resgate consolidado. Caixa recebido informado: {marketMoney(position.cash_received)}. Nenhum principal ou imposto foi deduzido pelo sistema.</p>}</details>
  </article>
}
