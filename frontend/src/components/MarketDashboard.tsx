import type { PortfolioValuation } from '../api'
import { marketMoney, marketPercent, marketQuantity, marketTone } from './market-format'
import './market-dashboard.css'
import { FinancialHint } from './FinancialHint'

const labels = {
  complete: 'Cobertura completa · cotações com atraso', stale: 'Avaliação desatualizada · último preço disponível',
  partial: 'Cobertura parcial · total indisponível', unavailable: 'Cotações indisponíveis', empty: 'Sem posições abertas',
}
function Reference({ value }: { value: string | null }) {
  if (!value || Number.isNaN(Date.parse(value))) return <span>Horário indisponível</span>
  return <time dateTime={value}>{new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo',
  }).format(new Date(value))} (Brasília)</time>
}
export function MarketDashboard({ snapshot, updating, failed, onRefresh }: {
  snapshot: PortfolioValuation; updating: boolean; failed: boolean; onRefresh: () => void
}) {
  const v = snapshot.valuation
  if (!v) return <section className="panel market-dashboard" aria-label="Avaliação de mercado"><p role="status">Avaliação de mercado indisponível nesta resposta.</p></section>
  // Incomplete coverage must not accidentally turn a subtotal into a confirmed total.
  const complete = v.is_complete && !['partial', 'unavailable'].includes(v.status)
  const value = complete ? snapshot.market_value : null
  const profit = complete ? v.unrealized_profit : null
  const percent = complete ? v.return_percent : null
  return <section className="market-dashboard" aria-label="Avaliação de mercado">
    <div className="market-status" role="status" aria-live="polite">
      <div><strong>{labels[v.status]}</strong><p>{v.covered_positions} de {v.total_positions} posições com preço utilizável. Estimativa em ações, sem saldo em caixa.</p>
        {v.status !== 'empty' && <p>As cotações do plano gratuito têm atraso esperado de cerca de 30 minutos; não são em tempo real.</p>}
        {failed && <p className="negative">Falha ao atualizar. Exibindo a última avaliação recebida, sem confirmação de atualização.</p>}
        {updating && <p>Atualizando avaliação; os valores anteriores permanecem identificados pelo horário.</p>}
      </div><button disabled={updating} onClick={onRefresh}>{updating ? 'Atualizando…' : 'Atualizar avaliação'}</button>
    </div>
    <div className="metrics market-metrics">
      <article className="metric featured"><div><span>Patrimônio a mercado · estimativa</span></div><h2>{marketMoney(value)}</h2><small>{complete ? 'Valor das posições abertas nos horários informados' : 'Sem total confirmado: faltam cotações utilizáveis'}</small></article>
      <article className="metric"><div><span>Resultado não realizado <FinancialHint label="resultado não realizado">Valor de mercado menos custo das posições abertas, incluindo taxas de compra. Custos de venda e tributos futuros não estão incluídos. Não é lucro líquido definitivo.</FinancialHint></span></div><h2 className={marketTone(profit)}>{marketMoney(profit)}</h2><small>Inclui taxas de compra; separado do resultado das vendas</small></article>
      <article className="metric"><div><span>Variação sobre custo aberto <FinancialHint label="variação sobre custo aberto">Resultado não realizado dividido pelo custo aberto, incluindo taxas de compra. Não é variação diária nem rentabilidade total da carteira: não inclui vendas, proventos ou saldo em caixa.</FinancialHint></span></div><h2 className={marketTone(percent)}>{marketPercent(percent)}</h2><small>Sobre custo com taxas; não é retorno total ou anualizado</small></article>
    </div>
    <p className="market-disclaimer">Estimativas antes de eventuais custos de venda e tributos futuros.</p>
    {!complete && <p className="market-partial">Subtotal parcial dos ativos cobertos: <strong>{marketMoney(v.partial_market_value)}</strong>. Não representa o patrimônio total.{v.missing_tickers.length > 0 && <> Sem preço utilizável: {v.missing_tickers.join(', ')}.</>}</p>}
    <div className="market-references"><span>Livro em <Reference value={snapshot.ledger_as_of}/></span><span>Avaliação calculada em <Reference value={v.calculated_at}/></span>
      {v.quoted_at_min && <span>Referências de cotação: <Reference value={v.quoted_at_min}/> a <Reference value={v.quoted_at_max}/></span>}</div>
    <article className="panel market-positions"><div className="panel-heading"><h3>Posições e avaliação de mercado</h3></div>
      {snapshot.holdings.length === 0 ? <p className="market-empty">Nenhuma posição aberta. O resultado realizado permanece no histórico.</p> :
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Posições com cotações e resultados"><table><caption className="sr-only">Posições do mesmo snapshot da avaliação; valores em reais</caption>
          <thead><tr><th scope="col">Ativo</th><th scope="col">Quantidade</th>
            <th scope="col">Preço de compra <FinancialHint label="preço de compra">Média ponderada dos preços negociados, sem taxas, da posição restante. Vendas parciais reduzem a base proporcionalmente; não usamos a primeira ou a última compra.</FinancialHint></th>
            <th scope="col">Preço médio de custo <FinancialHint label="preço médio de custo">Custo de aquisição restante, incluindo taxas de compra, dividido pela quantidade atual.</FinancialHint></th>
            <th scope="col">Custo aberto</th><th scope="col">Cotação</th>
            <th scope="col">Valorização sem taxas <FinancialHint label="valorização sem taxas">Cotação comparada à média negociada sem taxas da posição restante. Não é variação diária; pode ser positiva mesmo com resultado financeiro negativo por causa das taxas.</FinancialHint></th>
            {['Valor de mercado', 'Não realizado', 'Variação sobre custo', 'Referência da cotação'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{snapshot.holdings.map(h => <tr key={h.ticker}><th scope="row">{h.ticker}</th><td>{marketQuantity(h.quantity)}</td><td>{marketMoney(h.average_trade_price)}<small>Média sem taxas</small></td><td>{marketMoney(h.average_price)}<small>Inclui taxas de compra</small></td><td>{marketMoney(h.cost)}</td>
            <td>{marketMoney(h.quote.price)}<small>{h.quote.price == null ? 'Sem preço utilizável' : h.quote.is_stale || h.quote.status === 'stale' ? 'Desatualizada' : 'Válida no snapshot · atraso do plano'}</small></td>
            <td className={marketTone(h.quote.price == null ? null : h.price_appreciation_percent)}>{marketPercent(h.quote.price == null ? null : h.price_appreciation_percent)}</td>
            <td>{marketMoney(h.market_value)}</td><td className={marketTone(h.unrealized_profit)}>{marketMoney(h.unrealized_profit)}</td><td className={marketTone(h.return_percent)}>{marketPercent(h.return_percent)}</td>
            <td><Reference value={h.quote.quoted_at}/><small>Fonte: {h.quote.provider}{h.quote.from_cache ? ' · cache do servidor' : ''}</small>{h.quote.fetched_at && <small>Coletada em <Reference value={h.quote.fetched_at}/></small>}</td></tr>)}</tbody>
        </table></div>}
    </article>
  </section>
}
