import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Decimal from 'decimal.js'
import { ChartNoAxesCombined } from 'lucide-react'
import type { WealthObservation } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { formatFlowAxisTick } from './format'
import './portfolio.css'

const money = (value: string | number | null | undefined) => {
  if (value == null) return 'Indisponível'
  try {
    const [integer, fraction] = new Decimal(String(value)).toDecimalPlaces(2).toFixed(2).split('.')
    return `R$ ${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}`
  } catch { return 'Indisponível' }
}
const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR')
const today = () => new Date().toLocaleDateString('en-CA')
function idempotencyKey() {
  if (!globalThis.crypto?.randomUUID) throw new Error('Este navegador não oferece geração segura de identificadores. Atualize-o para registrar a observação.')
  return globalThis.crypto.randomUUID()
}

function snapshotChartRow(row: WealthObservation) {
  return {
    ...row,
    equities_plot: row.equities_market_value == null ? null : Number(row.equities_market_value),
    fixed_income_plot: row.fixed_income_net_value == null ? null : Number(row.fixed_income_net_value),
    total_plot: row.consolidated_net_value == null ? null : Number(row.consolidated_net_value),
  }
}

export function WealthEvolution({ repository, identity }: { repository: PrivateRepository; identity: string }) {
  const queryClient = useQueryClient()
  const [asOf, setAsOf] = useState(today)
  const [equitiesValue, setEquitiesValue] = useState('')
  const [source, setSource] = useState('')
  const [formError, setFormError] = useState('')
  const history = useQuery({ queryKey: ['wealth-observations', identity], queryFn: ({ signal }) => repository.wealthObservations(signal), retry: false })
  const save = useMutation({
    mutationFn: (input: { as_of: string; equities_market_value: string; equities_source: string }) =>
      repository.createWealthObservation(input, idempotencyKey()),
    onSuccess: async () => {
      setFormError('')
      setEquitiesValue('')
      setSource('')
      await queryClient.invalidateQueries({ queryKey: ['wealth-observations', identity] })
    },
    onError: error => setFormError(error instanceof Error ? error.message : 'Não foi possível registrar a observação.'),
  })
  const rows = history.data ?? []
  const chartData = useMemo(() => rows.map(snapshotChartRow), [rows])
  const latest = rows.at(-1)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    try {
      const value = new Decimal(equitiesValue.replace(',', '.'))
      if (!value.isFinite() || value.isNegative() || value.decimalPlaces() > 2) throw new Error('Informe um valor de ações válido com até duas casas decimais.')
      if (!source.trim()) throw new Error('Informe a origem do valor, por exemplo, extrato da corretora.')
      save.mutate({ as_of: asOf, equities_market_value: value.toFixed(2), equities_source: source.trim() })
    } catch (error) { setFormError(error instanceof Error ? error.message : 'Confira os campos informados.') }
  }

  return <article className="panel wealth-evolution" aria-label="Evolução patrimonial observada">
    <div className="panel-heading"><div><h3>Evolução patrimonial</h3><p>Observações por data, sem reconstruir preços ou saldos que não foram registrados</p></div><ChartNoAxesCombined size={18}/></div>
    <p className="wealth-evolution-note">Informe o valor total das ações conforme extrato da corretora. A renda fixa só entra se todos os contratos ativos tiverem uma observação de posição exatamente na mesma data. O total usa o valor líquido dos CDBs e não inclui caixa nem outros ativos.</p>
    <form className="wealth-observation-form" onSubmit={submit}>
      <label>Data-base<input type="date" value={asOf} max={today()} onChange={event => setAsOf(event.target.value)} required/></label>
      <label>Valor de mercado das ações<input type="number" min="0" step="0.01" inputMode="decimal" value={equitiesValue} onChange={event => setEquitiesValue(event.target.value)} placeholder="Ex.: 12500,00" required/></label>
      <label>Origem do valor<input type="text" maxLength={240} value={source} onChange={event => setSource(event.target.value)} placeholder="Ex.: extrato da corretora" required/></label>
      <button type="submit" disabled={save.isPending || history.isLoading}>{save.isPending ? 'Registrando…' : 'Registrar observação'}</button>
    </form>
    {formError && <p role="alert" className="wealth-observation-error">{formError}</p>}
    {history.isLoading ? <p role="status" className="empty compact">Carregando observações…</p>
      : history.isError ? <div role="alert" className="empty compact">Não foi possível carregar o histórico. <button type="button" onClick={() => void history.refetch()}>Tentar novamente</button></div>
        : rows.length === 0 ? <div className="empty compact"><h4>Sem observações patrimoniais ainda</h4><p>Registre o valor das ações por uma fonte identificada. Para incluir CDBs, registre também as posições de todos os contratos na mesma data.</p></div>
          : <>
            {latest?.fixed_income_coverage === 'partial' && <p role="status" className="portfolio-coverage">Renda fixa parcial em {dateLabel(latest.as_of)}; contratos sem observação nesta data: {latest.missing_fixed_income.join(', ')}. O total consolidado permanece indisponível.</p>}
            {latest?.fixed_income_coverage === 'unavailable' && <p role="status" className="portfolio-coverage">Nenhuma posição CDB tem observação em {dateLabel(latest.as_of)}. Registre posições datadas na página de renda fixa para habilitar essa classe no histórico.</p>}
            <div className="wealth-evolution-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 16, right: 14, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#222c33" strokeDasharray="3 5"/><XAxis dataKey="as_of" tickFormatter={value => new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })} axisLine={false} tickLine={false}/><YAxis tickFormatter={formatFlowAxisTick} axisLine={false} tickLine={false}/>
              <Tooltip labelFormatter={value => dateLabel(String(value))} formatter={(_value, name, item) => {
                const row = item.payload as WealthObservation
                const field = String(name) === 'Ações · fonte informada' ? row.equities_market_value : String(name) === 'Renda fixa líquida · observações' ? row.fixed_income_net_value : row.consolidated_net_value
                return [money(field), `${String(name)}${String(name).includes('Ações') && row.equities_source ? ` · ${row.equities_source}` : ''}`]
              }}/><Legend/>
              <Line type="monotone" dataKey="equities_plot" name="Ações · fonte informada" stroke="#8298f8" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false}/>
              <Line type="monotone" dataKey="fixed_income_plot" name="Renda fixa líquida · observações" stroke="#e8c77c" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false}/>
              <Line type="monotone" dataKey="total_plot" name="Total líquido das classes cobertas" stroke="#68e5b4" strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false}/>
            </LineChart></ResponsiveContainer></div>
            <div className="wealth-observation-table table-scroll"><table><caption className="sr-only">Observações patrimoniais e fontes registradas</caption><thead><tr><th scope="col">Data-base</th><th scope="col">Ações</th><th scope="col">Renda fixa · líquida</th><th scope="col">Total líquido</th><th scope="col">Origem</th></tr></thead><tbody>{[...rows].reverse().slice(0, 20).map(row => <tr key={`${row.as_of}:${row.id}`}><th scope="row">{dateLabel(row.as_of)}</th><td>{money(row.equities_market_value)}</td><td>{money(row.fixed_income_net_value)}<small>{row.fixed_income_coverage === 'partial' ? `Parcial · faltam ${row.missing_fixed_income.join(', ')}` : row.fixed_income_coverage === 'empty' ? 'Sem contratos CDB ativos' : row.fixed_income_coverage === 'unavailable' ? 'Sem observação na data' : 'Observações de todos os contratos'}</small></td><td>{money(row.consolidated_net_value)}</td><td>{row.equities_source ?? '—'}{row.fixed_income_sources.length > 0 && <small>CDB: {row.fixed_income_sources.map(item => `${item.asset} (${item.source})`).join('; ')}</small>}</td></tr>)}</tbody></table></div>
            <p className="wealth-evolution-footnote">As observações são persistidas por proprietário. Repetir uma data cria uma correção histórica; a mais recente prevalece no gráfico. Não é rentabilidade nem inclui saldo em caixa.</p>
          </>}
  </article>
}
