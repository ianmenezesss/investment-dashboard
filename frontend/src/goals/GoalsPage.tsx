import { useState } from 'react'
import type { FormEvent } from 'react'
import Decimal from 'decimal.js'
import { Check, Pencil, Plus, Target, Trash2, X } from 'lucide-react'
import { createGoal, goalProgressPercent, goalState, loadGoals, saveGoals, updateGoal, type Goal, type GoalDraft } from './goalStorage'
import './goals.css'

const emptyDraft: GoalDraft = { name: '', targetAmount: '', targetDate: '', initialReferenceAmount: '0' }
const money = (value: string | number) => { const [integer, fraction] = new Decimal(String(value)).toDecimalPlaces(2).toFixed(2).split('.'); return `R$ ${new Intl.NumberFormat('pt-BR').format(BigInt(integer))},${fraction}` }
const dateLabel = (value: string | null) => value ? new Date(`${value}T12:00:00`).toLocaleDateString('pt-BR') : 'Sem prazo definido'

export function GoalsPage({ identity }: { identity: string }) {
  const [loaded] = useState(() => { try { return { goals: loadGoals(identity), error: '' } } catch (error) { return { goals: [] as Goal[], error: (error as Error).message } } })
  const [goals, setGoals] = useState(loaded.goals)
  const [storageError, setStorageError] = useState(loaded.error)
  const [draft, setDraft] = useState<GoalDraft>(emptyDraft)
  const [editing, setEditing] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [formError, setFormError] = useState('')

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

  const active = goals.filter(goal => goalState(goal) !== 'completed')
  const completed = goals.filter(goal => goalState(goal) === 'completed')
  return <section className="goals-page" aria-label="Metas financeiras">
    <article className="panel goals-intro"><div><Target size={22}/><div><h2>Metas financeiras</h2><p>Defina seus objetivos e acompanhe o progresso com valores informados por você.</p></div></div><p className="goals-local-note">Metas salvas somente neste dispositivo e neste perfil do navegador. Elas não são sincronizadas entre dispositivos nem enviadas ao banco.</p></article>
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
    <section className="goals-list-section" aria-labelledby="active-goals-heading"><h2 id="active-goals-heading">Metas ativas ({active.length})</h2>{active.length ? <div className="goals-grid">{active.map(goal => <GoalCard key={goal.id} goal={goal} onEdit={beginEdit} onDelete={() => setDeleteId(goal.id)} deleting={deleteId === goal.id} onCancelDelete={() => setDeleteId(null)} onConfirmDelete={() => removeGoal(goal.id)}/>)}</div> : <div className="panel goals-empty"><Target size={20}/><h3>Nenhuma meta ativa</h3><p>Crie uma meta acima para começar a acompanhar.</p></div>}</section>
    <section className="goals-list-section" aria-labelledby="completed-goals-heading"><h2 id="completed-goals-heading">Metas concluídas ({completed.length})</h2>{completed.length ? <div className="goals-grid">{completed.map(goal => <GoalCard key={goal.id} goal={goal} onEdit={beginEdit} onDelete={() => setDeleteId(goal.id)} deleting={deleteId === goal.id} onCancelDelete={() => setDeleteId(null)} onConfirmDelete={() => removeGoal(goal.id)}/>)}</div> : <p className="goals-empty-note">Metas concluídas aparecerão aqui quando o valor confirmado atingir o alvo.</p>}</section>
  </section>
}

function GoalCard({ goal, onEdit, onDelete, deleting, onCancelDelete, onConfirmDelete }: { goal: Goal; onEdit: (goal: Goal) => void; onDelete: () => void; deleting: boolean; onCancelDelete: () => void; onConfirmDelete: () => void }) {
  const state = goalState(goal)
  const percent = goalProgressPercent(goal)
  const remaining = Decimal.min(goal.targetAmount, Decimal.max(0, new Decimal(goal.targetAmount).minus(goal.currentAmount))).toFixed(2)
  return <article className={`panel goal-card${state === 'completed' ? ' is-completed' : ''}`}>
    <div className="goal-card-heading"><div><h3>{goal.name}</h3><span className={`goal-state goal-${state}`}>{state === 'completed' ? 'Concluída' : state === 'overdue' ? 'Prazo vencido' : state === 'no-deadline' ? 'Sem prazo' : 'Ativa'}</span></div><div className="goal-card-actions"><button type="button" aria-label={`Editar meta ${goal.name}`} onClick={() => onEdit(goal)}><Pencil size={15}/></button><button type="button" aria-label={`Excluir meta ${goal.name}`} onClick={onDelete}><Trash2 size={15}/></button></div></div>
    <p className="goal-deadline">Prazo: {dateLabel(goal.targetDate)}</p><div className="goal-amounts"><span>Progresso manual informado<strong>{money(goal.currentAmount)}</strong></span><span>Valor-alvo<strong>{money(goal.targetAmount)}</strong></span></div>
    <div className="goal-progress-track" role="progressbar" aria-label={`Progresso de ${goal.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }}/></div>
    <div className="goal-progress-footer"><strong>{percent.toLocaleString('pt-BR')}%</strong>{new Decimal(remaining).isPositive() ? <span>Faltam {money(remaining)}</span> : <span>Alvo atingido</span>}</div>
    <p className="goal-source-note">Base inicial manual: {money(goal.initialReferenceAmount)} · sem cotação de mercado</p>
    {deleting && <div className="goal-delete-confirm" role="alertdialog" aria-label={`Confirmar exclusão de ${goal.name}`}><span>Excluir esta meta local?</span><button type="button" onClick={onConfirmDelete}>Excluir</button><button type="button" className="goals-secondary" onClick={onCancelDelete}>Cancelar</button></div>}
  </article>
}
