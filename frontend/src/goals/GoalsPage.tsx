import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import Decimal from 'decimal.js'
import { useQuery } from '@tanstack/react-query'
import { Check, Pencil, Plus, Target, Trash2, X } from 'lucide-react'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { createGoal, goalProgressPercent, goalState, loadGoals, saveGoals, updateGoal, updateGoalPlanning, type Goal, type GoalDraft, type GoalPlanningSettings } from './goalStorage'
import { confirmManualProgress, deriveInvestedBasis, goalForDisplay, setGoalToInvested, type InvestedBasis } from './goalProgress'
import { GoalPlanning } from './GoalPlanning'
import './goals.css'

const emptyDraft: GoalDraft = { name: '', targetAmount: '', targetDate: '', initialReferenceAmount: '0' }
const money = (value: string | number) => { const [integer, fraction] = new Decimal(String(value)).toDecimalPlaces(2).toFixed(2).split('.'); return `R$ ${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}` }
const dateLabel = (value: string | null) => value ? new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR') : 'Sem prazo definido'

export function GoalsPage({ identity, repository }: { identity: string; repository: PrivateRepository }) {
  const [loaded] = useState(() => { try { return { goals: loadGoals(identity), error: '' } } catch (error) { return { goals: [] as Goal[], error: (error as Error).message } } })
  const [goals, setGoals] = useState(loaded.goals)
  const [storageError, setStorageError] = useState(loaded.error)
  const [draft, setDraft] = useState<GoalDraft>(emptyDraft)
  const [editing, setEditing] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [formError, setFormError] = useState('')
  const performance = useQuery({ queryKey: ['financial-performance', identity], queryFn: ({ signal }) => repository.performance(signal), enabled: goals.length > 0, retry: false, staleTime: 5 * 60 * 1000 })
  const investedBasis = deriveInvestedBasis(performance.data, performance.isLoading, performance.isError)

  function persist(next: Goal[]) {
    try { saveGoals(identity, next); setGoals(next); setStorageError(''); return true }
    catch { setStorageError('Não foi possível salvar as metas neste dispositivo. As alterações não foram aplicadas.'); return false }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setFormError('')
    try {
      const next = editing ? goals.map(goal => goal.id === editing ? updateGoal(goal, draft) : goal) : [...goals, createGoal(draft)]
      if (persist(next)) { setDraft(emptyDraft); setEditing(null) }
    } catch (error) { setFormError((error as Error).message) }
  }
  function beginEdit(goal: Goal) {
    setEditing(goal.id); setDraft({ name: goal.name, targetAmount: goal.targetAmount, targetDate: goal.targetDate ?? '', initialReferenceAmount: goal.initialReferenceAmount }); setFormError('')
  }
  function removeGoal(id: string) {
    if (persist(goals.filter(goal => goal.id !== id))) setDeleteId(null)
  }
  function useInvested(id: string) {
    persist(goals.map(goal => goal.id === id ? setGoalToInvested(goal) : goal))
  }
  function confirmManual(id: string, value: string) {
    try {
      const next = goals.map(goal => goal.id === id ? confirmManualProgress(goal, value) : goal)
      if (persist(next)) return ''
      return 'Não foi possível salvar a confirmação manual.'
    } catch (error) { return (error as Error).message }
  }
  function savePlanning(id: string, planning: GoalPlanningSettings) {
    try {
      const next = goals.map(goal => goal.id === id ? updateGoalPlanning(goal, planning) : goal)
      return persist(next) ? '' : 'Não foi possível salvar as premissas neste dispositivo.'
    } catch (error) { return (error as Error).message }
  }

  const displayGoals = goals.map(goal => goalForDisplay(goal, investedBasis))
  const active = displayGoals.filter(goal => goalState(goal) !== 'completed')
  const completed = displayGoals.filter(goal => goalState(goal) === 'completed')
  return <section className="goals-page" aria-label="Metas financeiras">
    <article className="panel goals-intro"><div><Target size={22}/><div><h2>Metas financeiras</h2><p>Defina seus objetivos e acompanhe o progresso com valores informados por você.</p></div></div><p className="goals-local-note">Metas salvas somente neste dispositivo e neste perfil do navegador. Elas não são sincronizadas entre dispositivos nem enviadas ao banco.</p></article>
    {goals.length > 0 && <InvestedBasisNotice basis={investedBasis}/>}
    {storageError && <p role="alert" className="goals-error">{storageError}</p>}
    <article className="panel goals-editor"><div className="panel-heading"><div><h3>{editing ? 'Editar meta' : 'Criar meta'}</h3><p>O valor de referência inicial é manual e não representa uma avaliação automática da carteira.</p></div></div>
      <form onSubmit={submit}>
        <label>Nome da meta<input name="name" required minLength={2} maxLength={80} value={draft.name} onChange={event => setDraft(value => ({ ...value, name: event.target.value }))} placeholder="Ex.: Reserva para imóvel"/></label>
        <label>Valor-alvo (R$)<input name="targetAmount" required type="number" min="0.01" max="1000000000000" step="0.01" value={draft.targetAmount} onChange={event => setDraft(value => ({ ...value, targetAmount: event.target.value }))} placeholder="100000,00"/></label>
        <label>Prazo (opcional)<input name="targetDate" type="date" value={draft.targetDate ?? ''} onChange={event => setDraft(value => ({ ...value, targetDate: event.target.value }))}/></label>
        <label>Valor inicial de referência (R$)<input name="initialReferenceAmount" required type="number" min="0" max="1000000000000" step="0.01" value={draft.initialReferenceAmount} onChange={event => setDraft(value => ({ ...value, initialReferenceAmount: event.target.value }))}/></label>
        {formError && <p role="alert" className="goals-error">{formError}</p>}
        <div className="goals-editor-actions"><button type="submit"><Check size={15}/>{editing ? 'Salvar alterações' : 'Adicionar meta'}</button>{editing && <button type="button" className="goals-secondary" onClick={() => { setEditing(null); setDraft(emptyDraft); setFormError('') }}><X size={15}/>Cancelar</button>}</div>
      </form>
    </article>
    <section className="goals-list-section" aria-labelledby="active-goals-heading"><h2 id="active-goals-heading">Metas ativas ({active.length})</h2>{active.length ? <div className="goals-grid">{active.map(goal => <GoalCard key={goal.id} goal={goal} investedBasis={investedBasis} onUseInvested={useInvested} onConfirmManual={confirmManual} onSavePlanning={savePlanning} onEdit={beginEdit} onDelete={() => setDeleteId(goal.id)} deleting={deleteId === goal.id} onCancelDelete={() => setDeleteId(null)} onConfirmDelete={() => removeGoal(goal.id)}/>)}</div> : <div className="panel goals-empty"><Target size={20}/><h3>Nenhuma meta ativa</h3><p>Crie uma meta acima para começar a acompanhar.</p></div>}</section>
    <section className="goals-list-section" aria-labelledby="completed-goals-heading"><h2 id="completed-goals-heading">Metas concluídas ({completed.length})</h2>{completed.length ? <div className="goals-grid">{completed.map(goal => <GoalCard key={goal.id} goal={goal} investedBasis={investedBasis} onUseInvested={useInvested} onConfirmManual={confirmManual} onSavePlanning={savePlanning} onEdit={beginEdit} onDelete={() => setDeleteId(goal.id)} deleting={deleteId === goal.id} onCancelDelete={() => setDeleteId(null)} onConfirmDelete={() => removeGoal(goal.id)}/>)}</div> : <p className="goals-empty-note">Metas concluídas aparecerão aqui quando o valor confirmado atingir o alvo.</p>}</section>
  </section>
}

function InvestedBasisNotice({ basis }: { basis: InvestedBasis }) {
  return <aside className={`goals-basis-notice basis-${basis.status}`} role={basis.status === 'partial' || basis.status === 'unavailable' ? 'status' : 'note'}>
    {basis.status === 'loading' ? <p>Consultando o capital investido registrado… O valor manual continua disponível.</p>
      : basis.status === 'unavailable' ? <p>{basis.warnings.join(' ')} Atualize o progresso manualmente.</p>
        : <><p>Capital investido é custo aberto de ações + principal efetivo de renda fixa{basis.asOf ? ` · base em ${dateLabel(basis.asOf)}` : ''}. Não é patrimônio de mercado e não inclui caixa externo nem proventos.</p>
          {basis.status === 'partial' && <p>Base incompleta: {basis.warnings.join('; ')}. Posições declaradas sem saldo contábil ficam excluídas. Você pode usar valor manual.</p>}
          {basis.status === 'available' && <p>Os valores declarados sem posição contábil e cotações de mercado não entram na base. Você pode usar valor manual a qualquer momento.</p>}</>}
  </aside>
}

function GoalCard({ goal, investedBasis, onUseInvested, onConfirmManual, onSavePlanning, onEdit, onDelete, deleting, onCancelDelete, onConfirmDelete }: { goal: Goal; investedBasis: InvestedBasis; onUseInvested: (id: string) => void; onConfirmManual: (id: string, value: string) => string; onSavePlanning: (id: string, settings: GoalPlanningSettings) => string; onEdit: (goal: Goal) => void; onDelete: () => void; deleting: boolean; onCancelDelete: () => void; onConfirmDelete: () => void }) {
  const [manualEditing, setManualEditing] = useState(false)
  const [planningOpen, setPlanningOpen] = useState(false)
  const [manualValue, setManualValue] = useState(goal.manualProgressAmount)
  const [manualError, setManualError] = useState('')
  useEffect(() => { setManualValue(goal.manualProgressAmount) }, [goal.manualProgressAmount])
  const state = goalState(goal)
  const percent = goalProgressPercent(goal)
  const remaining = Decimal.min(goal.targetAmount, Decimal.max(0, new Decimal(goal.targetAmount).minus(goal.currentAmount))).toFixed(2)
  return <article className={`panel goal-card${state === 'completed' ? ' is-completed' : ''}`}>
    <div className="goal-card-heading"><div><h3>{goal.name}</h3><span className={`goal-state goal-${state}`}>{state === 'completed' ? 'Concluída' : state === 'overdue' ? 'Prazo vencido' : state === 'no-deadline' ? 'Sem prazo' : 'Ativa'}</span></div><div className="goal-card-actions"><button type="button" aria-label={`Editar meta ${goal.name}`} onClick={() => onEdit(goal)}><Pencil size={15}/></button><button type="button" aria-label={`Excluir meta ${goal.name}`} onClick={onDelete}><Trash2 size={15}/></button></div></div>
    <p className="goal-deadline">Prazo: {dateLabel(goal.targetDate)}</p><div className="goal-amounts"><span>{goal.progressSource === 'invested' && investedBasis.amount !== null ? 'Capital investido · custo/principal aberto' : goal.progressSource === 'invested' ? 'Último progresso manual · base indisponível' : 'Patrimônio informado manualmente'}<strong>{money(goal.currentAmount)}</strong></span><span>Valor-alvo<strong>{money(goal.targetAmount)}</strong></span></div>
    <div className="goal-progress-track" role="progressbar" aria-label={`Progresso de ${goal.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }}/></div>
    <div className="goal-progress-footer"><strong>{percent.toLocaleString('pt-BR')}%</strong>{new Decimal(remaining).isPositive() ? <span>Faltam {money(remaining)}</span> : <span>Alvo atingido</span>}</div>
    <p className="goal-source-note">{goal.progressSource === 'invested' && investedBasis.amount !== null ? `Capital investido não representa patrimônio de mercado${investedBasis.asOf ? ` · data-base ${dateLabel(investedBasis.asOf)}` : ''}.` : `Última confirmação manual: ${goal.manualConfirmedAt ? new Date(goal.manualConfirmedAt).toLocaleString('pt-BR') : 'sem confirmação'}.`} Referência inicial: {money(goal.initialReferenceAmount)}.</p>
    <div className="goal-progress-actions">{goal.progressSource !== 'invested' && investedBasis.amount !== null && <button type="button" onClick={() => { onUseInvested(goal.id); setManualEditing(false); setManualError('') }}>Acompanhar capital investido</button>}<button type="button" className="goals-secondary" onClick={() => { setManualEditing(value => !value); setManualError(''); setManualValue(goal.manualProgressAmount) }}>{manualEditing ? 'Cancelar atualização' : goal.progressSource === 'manual' ? 'Atualizar valor manual' : 'Usar progresso manual'}</button></div>
    {manualEditing && <form className="goal-manual-form" onSubmit={event => { event.preventDefault(); const error = onConfirmManual(goal.id, manualValue); setManualError(error); if (!error) setManualEditing(false) }}><label>Patrimônio atual usado nesta meta (R$)<input name="manualProgressAmount" type="number" min="0" max="1000000000000" step="0.01" value={manualValue} onChange={event => setManualValue(event.target.value)} required/></label><button type="submit"><Check size={14}/>Confirmar valor manual</button>{manualError && <p role="alert">{manualError}</p>}</form>}
    {goal.progressSource === 'invested' && investedBasis.status === 'partial' && <p className="goal-incomplete-warning" role="status">Base de capital investido parcial: {investedBasis.warnings.join('; ')}. Confira a composição ou use o valor manual.</p>}
    <button type="button" className="goal-planning-toggle" aria-expanded={planningOpen} onClick={() => setPlanningOpen(value => !value)}><Plus size={14}/>{planningOpen ? 'Fechar planejamento' : 'Planejar aportes e projeções'}</button>
    {planningOpen && <GoalPlanning currentAmount={goal.currentAmount} targetAmount={goal.targetAmount} targetDate={goal.targetDate} settings={goal.planning} onSave={settings => onSavePlanning(goal.id, settings)}/>}
    {deleting && <div className="goal-delete-confirm" role="alertdialog" aria-label={`Confirmar exclusão de ${goal.name}`}><span>Excluir esta meta local?</span><button type="button" onClick={onConfirmDelete}>Excluir</button><button type="button" className="goals-secondary" onClick={onCancelDelete}>Cancelar</button></div>}
  </article>
}
