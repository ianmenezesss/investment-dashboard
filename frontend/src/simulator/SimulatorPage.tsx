import { useMemo, useState } from 'react'
import Decimal from 'decimal.js'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { simulateScenario, validateInputs, type SimulationInput, type Timing } from './simulation'
import './simulator.css'

const defaults = { initial: '1000', monthly: '500', months: '120', inflation: '4', conservative: '6', moderate: '10', optimistic: '14' }
const money = (value: Decimal) => `R$ ${value.toDecimalPlaces(2).toNumber().toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const decimalField = (value: string) => { try { return new Decimal(value || 'NaN') } catch { return new Decimal(Number.NaN) } }

export function SimulatorPage() {
  const [fields, setFields] = useState(defaults)
  const [includeInflation, setIncludeInflation] = useState(false)
  const [timing, setTiming] = useState<Timing>('end')
  const [showReal, setShowReal] = useState(false)
  const inputValidation = validateInputs({ ...fields, includeInflation })
  const rateErrors = (['conservative', 'moderate', 'optimistic'] as const).flatMap(key => {
    const value = decimalField(fields[key])
    return !value.isFinite() || value.lte(-100) || value.gt(500) ? [`Cenário ${key}: a taxa deve ser maior que -100% e no máximo 500%.`] : []
  })
  const errors = [...inputValidation.errors, ...rateErrors]
  const input = useMemo<SimulationInput | null>(() => {
    if (!inputValidation.valid || rateErrors.length) return null
    return { initial: inputValidation.initial, monthly: inputValidation.monthly, months: inputValidation.months,
      inflation: inputValidation.inflation, includeInflation, timing }
  }, [fields, includeInflation, timing, inputValidation.valid, rateErrors.length])
  const results = useMemo(() => input ? (['conservative', 'moderate', 'optimistic'] as const).map(key => ({
    key, label: key === 'conservative' ? 'Conservador' : key === 'moderate' ? 'Moderado' : 'Otimista',
    result: simulateScenario(input, decimalField(fields[key])), color: key === 'conservative' ? '#8298f8' : key === 'moderate' ? '#68e5b4' : '#e8c77c',
  })) : [], [input, fields.conservative, fields.moderate, fields.optimistic])
  const chartData = useMemo(() => {
    const maxMonths = input?.months ?? 0
    return Array.from({ length: maxMonths + 1 }, (_, month) => {
      const point: Record<string, number> = { month, invested: results[0]?.result.points[month]?.[showReal ? 'investedReal' : 'investedNominal'].toNumber() ?? 0 }
      results.forEach(({ key, result }) => { point[key] = result.points[month]?.[showReal ? 'balanceReal' : 'balanceNominal'].toNumber() ?? 0 })
      return point
    })
  }, [input?.months, results, showReal])
  const update = (key: keyof typeof defaults, value: string) => setFields(current => ({ ...current, [key]: value }))
  return <section className="panel simulator-page" aria-label="Simulador hipotético de investimentos">
    <div className="panel-heading"><div><h2>Simulador de investimentos</h2><p>Cenários matemáticos hipotéticos. As taxas são premissas editáveis, não previsões nem recomendação.</p></div><button type="button" className="simulator-reset" onClick={() => { setFields(defaults); setIncludeInflation(false); setTiming('end'); setShowReal(false) }}>Restaurar padrão</button></div>
    <div className="simulator-form">
      <label>Valor inicial (R$)<input inputMode="decimal" type="number" min="0" max="1000000000" step="0.01" value={fields.initial} onChange={event => update('initial', event.target.value)}/></label>
      <label>Aporte mensal (R$)<input inputMode="decimal" type="number" min="0" max="100000000" step="0.01" value={fields.monthly} onChange={event => update('monthly', event.target.value)}/></label>
      <label>Prazo (meses)<input type="number" min="1" max="600" step="1" value={fields.months} onChange={event => update('months', event.target.value)}/></label>
      <label>Aportes<select value={timing} onChange={event => setTiming(event.target.value as Timing)}><option value="end">No fim do mês</option><option value="beginning">No início do mês</option></select></label>
    </div>
    <div className="simulator-assumptions">
      {(['conservative', 'moderate', 'optimistic'] as const).map(key => <label key={key}>{key === 'conservative' ? 'Taxa conservadora' : key === 'moderate' ? 'Taxa moderada' : 'Taxa otimista'} (% ao ano)<input type="number" min="-99.99" max="500" step="0.1" value={fields[key]} onChange={event => update(key, event.target.value)}/></label>)}
    </div>
    <div className="simulator-inflation"><label><input type="checkbox" checked={includeInflation} onChange={event => { setIncludeInflation(event.target.checked); if (!event.target.checked) setShowReal(false) }}/> Considerar inflação</label>{includeInflation && <label>Inflação anual hipotética (%)<input type="number" min="0" max="1000" step="0.1" value={fields.inflation} onChange={event => update('inflation', event.target.value)}/></label>}<label className="simulator-real-toggle"><input type="checkbox" checked={showReal} disabled={!includeInflation} onChange={event => setShowReal(event.target.checked)}/> Gráfico em valores reais de hoje</label></div>
    {errors.length > 0 && <div className="simulator-errors" role="alert"><strong>Revise os parâmetros:</strong><ul>{errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
    {input && <>
      <div className="simulator-results">{results.map(({ key, label, result, color }) => <article key={key} style={{ borderTopColor: color }}><h3>{label} · {result.annualRate.toString()}% a.a.</h3><p>Patrimônio final nominal<strong>{money(result.finalNominal)}</strong></p><p>Total aportado nominal<strong>{money(result.totalInvested)}</strong></p><p>Rendimento projetado nominal<strong>{money(result.gainNominal)}</strong></p>{includeInflation && <><p>Patrimônio em reais de hoje<strong>{money(result.finalReal)}</strong></p><p>Aportes em reais de hoje<strong>{money(result.totalInvestedReal)}</strong></p><p>Rendimento real estimado<strong>{money(result.gainReal)}</strong></p></>}</article>)}</div>
      <div className="simulator-chart-heading"><h3>Evolução mensal {showReal ? 'em valores reais de hoje' : 'nominal'}</h3><p>O total aportado aparece como referência e não inclui rendimento.</p></div>
      <div className="simulator-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 10, right: 16, left: 12, bottom: 4 }}><CartesianGrid vertical={false} stroke="#25313a" strokeDasharray="3 5"/><XAxis dataKey="month" tick={{ fill: '#9aabb4', fontSize: 10 }} tickFormatter={value => `${value}m`}/><YAxis tick={{ fill: '#9aabb4', fontSize: 10 }} tickFormatter={value => new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}/><Tooltip formatter={value => money(new Decimal(Number(value)))} labelFormatter={value => `Mês ${value}`}/><Legend formatter={name => ({ conservative: `Conservador · ${fields.conservative}%`, moderate: `Moderado · ${fields.moderate}%`, optimistic: `Otimista · ${fields.optimistic}%`, invested: 'Total aportado' }[String(name)] ?? String(name))}/><Line dataKey="invested" name="invested" stroke="#b6c2ca" strokeDasharray="5 4" dot={false} isAnimationActive={false}/><Line dataKey="conservative" name="conservative" stroke="#8298f8" dot={false} isAnimationActive={false}/><Line dataKey="moderate" name="moderate" stroke="#68e5b4" dot={false} isAnimationActive={false}/><Line dataKey="optimistic" name="optimistic" stroke="#e8c77c" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div>
      <div className="simulator-formula"><strong>Fórmula e convenção:</strong> taxa mensal equivalente = (1 + taxa anual efetiva)^(1/12) − 1. Os juros são aplicados mensalmente; aportes ocorrem no início ou no fim do mês conforme selecionado. Valores são calculados com precisão decimal e arredondados apenas para exibição.</div>
    </>}
    <p className="simulator-disclaimer">Esta simulação é independente da carteira real e não lê nem altera operações, eventos ou saldos. Não inclui impostos, taxas, liquidez, volatilidade ou garantias de retorno. Inflação usa taxa anual efetiva editável.</p>
  </section>
}
