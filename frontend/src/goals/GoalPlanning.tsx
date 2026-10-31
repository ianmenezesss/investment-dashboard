import { useEffect, useMemo, useState, type FormEvent } from 'react'
import Decimal from 'decimal.js'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { calculateGoalPlan } from './planningMath'
import { validateGoalPlanningSettings, type GoalPlanningSettings } from './goalStorage'
import './goals.css'

const money = (value: Decimal | string | number) => { const [integer, fraction] = new Decimal(value).toDecimalPlaces(2).toFixed(2).split('.'); return `R$ ${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}` }
const decimalField = (value: string) => { try { return new Decimal(value) } catch { return new Decimal(Number.NaN) } }

export function GoalPlanning({ currentAmount, targetAmount, targetDate, settings: saved, onSave }: { currentAmount: string; targetAmount: string; targetDate: string | null; settings: GoalPlanningSettings; onSave: (settings: GoalPlanningSettings) => string }) {
  const [settings, setSettings] = useState(saved)
  const [saveError, setSaveError] = useState('')
  const [savedNotice, setSavedNotice] = useState('')
  useEffect(() => setSettings(saved), [saved])
  const calculation = useMemo(() => {
    try { return { plan: calculateGoalPlan({ currentAmount, targetAmount, targetDate, settings }), error: '' } }
    catch (error) { return { plan: null, error: (error as Error).message } }
  }, [currentAmount, targetAmount, targetDate, settings])
  const valid = (() => { try { validateGoalPlanningSettings(settings); return true } catch { return false } })()
  function update(key: keyof GoalPlanningSettings, value: string | boolean) { setSavedNotice(''); setSettings(current => ({ ...current, [key]: value })) }
  function updateRate(key: keyof GoalPlanningSettings['annualRates'], value: string) { setSavedNotice(''); setSettings(current => ({ ...current, annualRates: { ...current.annualRates, [key]: value } })) }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaveError(''); setSavedNotice('')
    try {
      const normalized = validateGoalPlanningSettings(settings)
      const error = onSave(normalized)
      if (error) setSaveError(error)
      else { setSettings(normalized); setSavedNotice('Premissas salvas neste dispositivo.') }
    } catch (error) { setSaveError((error as Error).message) }
  }
  const plan = calculation.plan
  const current = decimalField(currentAmount)
  const target = decimalField(targetAmount)
  const gap = Decimal.max(0, target.minus(current))
  const horizonDescription = plan?.horizon === 'deadline' ? `até o prazo da meta (${plan.months} meses)` : plan?.horizon === 'expired' ? `horizonte manual de ${plan.months} meses porque o prazo venceu` : plan?.horizon === 'today' ? `horizonte manual de ${plan.months} meses · prazo é hoje` : `horizonte hipotético de ${plan?.months ?? settings.horizonMonths} meses`
  return <section className="goal-planning" aria-label="Planejamento hipotético de aportes">
    <form onSubmit={save}>
      <div className="goal-plan-heading"><div><h4>Planejamento de aportes</h4><p>Hipóteses matemáticas; não são previsão nem promessa de rentabilidade.</p></div><span className="tag">{horizonDescription}</span></div>
      <div className="goal-plan-summary"><div><span>Diferença até o alvo</span><strong>{money(gap)}</strong></div><div><span>Base usada na projeção</span><strong>{money(current)}</strong><small>{targetDate ? 'valor atual do progresso selecionado; confira se representa patrimônio ou custo investido' : 'valor atual do progresso selecionado'}</small></div></div>
      <div className="goal-plan-inputs">
        <label>Aporte mensal que você planeja (R$)<input name="plannedMonthlyContribution" type="number" min="0" max="100000000" step="0.01" value={settings.monthlyContribution} onChange={event => update('monthlyContribution', event.target.value)}/></label>
        <label>Horizonte manual (meses)<input name="horizonMonths" type="number" min="1" max="600" step="1" value={settings.horizonMonths} disabled={!!targetDate && calculation.plan?.horizon === 'deadline'} onChange={event => update('horizonMonths', event.target.value)}/></label>
        {targetDate && calculation.plan?.horizon !== 'expired' && <label className="goal-plan-toggle"><input name="useManualHorizon" type="checkbox" checked={settings.useManualHorizon} onChange={event => update('useManualHorizon', event.target.checked)}/>Usar horizonte manual em vez do prazo da meta</label>}
        <label>Hipótese conservadora (% ao ano)<input name="annualRateConservative" type="number" min="-99.9" max="500" step="0.1" value={settings.annualRates.conservative} onChange={event => updateRate('conservative', event.target.value)}/></label>
        <label>Hipótese moderada (% ao ano)<input name="annualRateModerate" type="number" min="-99.9" max="500" step="0.1" value={settings.annualRates.moderate} onChange={event => updateRate('moderate', event.target.value)}/></label>
        <label>Hipótese otimista (% ao ano)<input name="annualRateOptimistic" type="number" min="-99.9" max="500" step="0.1" value={settings.annualRates.optimistic} onChange={event => updateRate('optimistic', event.target.value)}/></label>
      </div>
      {targetDate && calculation.plan?.horizon === 'expired' && <p className="goal-plan-expired">Prazo vencido em {new Date(`${targetDate}T12:00:00`).toLocaleDateString('pt-BR')}. A projeção usa o horizonte manual informado.</p>}
      {calculation.error && <p className="goal-plan-error" role="alert">{calculation.error}</p>}
      {saveError && <p className="goal-plan-error" role="alert">{saveError}</p>}{savedNotice && <p className="goal-plan-saved" role="status">{savedNotice}</p>}
      <div className="goal-plan-scenarios">{plan?.scenarios.map(scenario => <article key={scenario.key} style={{ borderTopColor: scenario.color }}><h5>{scenario.label} · {scenario.annualRate.toString()}% a.a.</h5><p>Aporte mensal necessário {horizonDescription}<strong>{money(scenario.requiredMonthly)}</strong></p><p>Tempo com aporte planejado<strong>{scenario.monthsToGoal === null ? 'Mais de 600 meses' : scenario.monthsToGoal === 0 ? 'Alvo já atingido' : `${scenario.monthsToGoal} ${scenario.monthsToGoal === 1 ? 'mês' : 'meses'}`}</strong></p><p>Projeção no horizonte<strong>{money(scenario.projected.finalNominal)}</strong></p></article>)}</div>
      {plan && <><div className="goal-plan-chart-heading"><h5>Evolução projetada</h5><p>{plan.months} meses · aportes no fim do mês · valores nominais hipotéticos</p></div><div className="goal-plan-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={plan.chart} margin={{ top: 12, right: 12, left: 6, bottom: 4 }}><CartesianGrid vertical={false} stroke="#25313a" strokeDasharray="3 5"/><XAxis dataKey="month" tick={{ fill: '#9aabb4', fontSize: 9 }} tickFormatter={value => `${value}m`}/><YAxis tick={{ fill: '#9aabb4', fontSize: 9 }} tickFormatter={value => new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}/><Tooltip formatter={value => money(Number(value))} labelFormatter={value => `Mês ${value}`}/><Legend formatter={value => ({ baseAndContributions: 'Base + aportes previstos', conservative: 'Conservador', moderate: 'Moderado', optimistic: 'Otimista' }[String(value)] ?? String(value))}/><ReferenceLine y={Number(targetAmount)} stroke="#d9e1dc" strokeDasharray="4 4" label={{ value: 'Alvo', fill: '#d9e1dc', fontSize: 10 }}/><Line dataKey="baseAndContributions" stroke="#b6c2ca" strokeDasharray="5 4" dot={false} isAnimationActive={false}/><Line dataKey="conservative" stroke="#8298f8" dot={false} isAnimationActive={false}/><Line dataKey="moderate" stroke="#68e5b4" dot={false} isAnimationActive={false}/><Line dataKey="optimistic" stroke="#e8c77c" dot={false} isAnimationActive={false}/></LineChart></ResponsiveContainer></div></>}
      <button type="submit" className="goal-plan-save" disabled={!valid}>Salvar premissas</button>
      <p className="goal-plan-disclaimer">A taxa mensal equivalente e os aportes no fim do mês seguem a convenção do Simulador. Se a base for capital investido, a projeção começa pelo custo/principal registrado e não afirma que esse valor seja patrimônio de mercado. Sem cotação atualizada, esta tela não calcula rentabilidade real.</p>
    </form>
  </section>
}
