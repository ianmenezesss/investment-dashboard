import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Landmark, Plus } from 'lucide-react'
import { ApiError } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { Button } from '../components/ui/button'
import { FinancialHint } from '../components/FinancialHint'
import { marketMoney } from '../components/market-format'
import { FixedIncomeDialog, type DialogMode, type WriteMode } from './FixedIncomeDialog'
import { FixedIncomeReturns } from './FixedIncomeReturns'
import { contractLabel, dayLabel, exceeds, positive, totalApplications } from './format'
import type { CdbInput } from './types'
import './fixed-income.css'
import { ManualPositionDialog } from './ManualPositionDialog'
import { ObservedPositionSummary } from './ObservedPosition'
import type { ObservedPositionInput } from './types'
import { ApplicationRevisionDialog, type RevisionKind } from './ApplicationRevisionDialog'
import { ApplicationRevisionHistory } from './ApplicationRevisionHistory'
import type { CdbMovement } from './types'

export function FixedIncomePage({ repository, identity, newOperationRequest, onAuthError }: {
  repository: PrivateRepository; identity: string; newOperationRequest: number; onAuthError: (error: ApiError) => void
}) {
  const [params, setParams] = useSearchParams()
  const rawId = params.get('investment')
  const selected = rawId && /^[1-9]\d*$/.test(rawId) && Number.isSafeInteger(Number(rawId)) ? Number(rawId) : null
  const [offset, setOffset] = useState(0)
  const [mode, setMode] = useState<DialogMode>(null)
  const [manualMode, setManualMode] = useState<'opening' | 'observation' | null>(null)
  const [revisionTarget, setRevisionTarget] = useState<{ movement: CdbMovement; kind: RevisionKind } | null>(null)
  const [writeError, setWriteError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [epoch, setEpoch] = useState(0)
  const active = useRef(true), submitting = useRef(false), controller = useRef<AbortController | null>(null)
  const focus = useRef<HTMLElement | null>(null), seenRequest = useRef(newOperationRequest)
  const client = useQueryClient()
  const prefix = ['fixed-income', identity]
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false; controller.current?.abort()
      // Aborting HTTP cannot prove that a POST was not committed by the server.
      if (submitting.current) void client.invalidateQueries({ queryKey: ['fixed-income', identity], refetchType: 'none' })
    }
  }, [client, identity])
  function open(next: DialogMode) { focus.current = document.activeElement as HTMLElement; setWriteError(''); setMode(next) }
  useEffect(() => { if (newOperationRequest !== seenRequest.current) { seenRequest.current = newOperationRequest; focus.current = document.activeElement as HTMLElement; setWriteError(''); setMode('choose') } }, [newOperationRequest])
  const list = useQuery({ queryKey: [...prefix, 'list', offset], queryFn: ({ signal }) => repository.cdbs(offset, signal), retry: false, staleTime: 60000, refetchOnWindowFocus: false })
  const detail = useQuery({ queryKey: [...prefix, 'detail', selected], queryFn: ({ signal }) => repository.cdb(selected!, signal), enabled: selected !== null, retry: false, staleTime: 60000, refetchOnWindowFocus: false })
  const history = useInfiniteQuery({ queryKey: [...prefix, 'movements', selected], initialPageParam: 0,
    queryFn: ({ signal, pageParam }) => repository.cdbMovements(selected!, pageParam, signal), enabled: selected !== null,
    getNextPageParam: (last, _pages, page) => last.length === 100 ? page + 100 : undefined,
    retry: false, staleTime: 60000, refetchOnWindowFocus: false })
  const originalHistory = useInfiniteQuery({ queryKey: [...prefix, 'original-movements', selected], initialPageParam: 0,
    queryFn: ({ signal, pageParam }) => repository.cdbOriginalMovements(selected!, pageParam, signal), enabled: selected !== null,
    getNextPageParam: (last, _pages, page) => last.length === 100 ? page + 100 : undefined,
    retry: false, staleTime: 60000, refetchOnWindowFocus: false })
  const observations = useInfiniteQuery({ queryKey: [...prefix, 'observations', selected], initialPageParam: 0,
    queryFn: ({signal,pageParam}) => repository.cdbObservations(selected!,pageParam,signal), enabled: !!selected && detail.data?.tracking_mode==='CONSOLIDATED',
    getNextPageParam:(last,_pages,page)=>last.length===100?page+100:undefined,retry:false,staleTime:60000,refetchOnWindowFocus:false })
  const errors = [list.error, detail.error, history.error, originalHistory.error, observations.error]
  const authError = errors.find(error => error instanceof ApiError && error.status === 401) || errors.find(error => error instanceof ApiError && error.status === 403)
  useEffect(() => { if (authError instanceof ApiError) onAuthError(authError) }, [authError, onAuthError])
  const rows = history.data?.pages.flat() ?? []
  const originalRows = originalHistory.data?.pages.flat() ?? []
  const completeHistory = !!history.data && !history.hasNextPage && !history.isError
  function invalidate() {
    setEpoch(value => value + 1)
    client.removeQueries({ queryKey: [...prefix, 'returns'] })
    void client.invalidateQueries({ queryKey: prefix })
    void client.invalidateQueries({ queryKey: ['summary', identity] })
  }
  function openManual(kind:'opening'|'observation') {focus.current=document.activeElement as HTMLElement;setWriteError('');setManualMode(kind)}
  async function saveManual(input:ObservedPositionInput) {
    if(submitting.current||!selected)return
    submitting.current=true;setBusy(true);setWriteError('');controller.current=new AbortController()
    try {
      await repository.saveCdbObservation(selected,input,manualMode==='opening',controller.current.signal)
      if(!active.current)return
      setManualMode(null);setSuccess('Posição informada salva. Nenhuma aplicação ou amortização foi criada.');invalidate()
    }catch(cause){if(!active.current)return;if(cause instanceof ApiError&&[401,403].includes(cause.status)){setManualMode(null);onAuthError(cause)}else{setWriteError((cause as Error).message+' Confira as posições antes de reenviar se o resultado não foi confirmado.');if(cause instanceof TypeError||cause instanceof ApiError&&cause.status>=500)invalidate()}}
    finally{submitting.current=false;if(active.current)setBusy(false)}
  }
  async function archiveEmptyContract() {
    if (submitting.current || !selected || !detail.data || detail.data.lots.length || detail.data.opening_balance || detail.data.latest_observation) return
    const label = detail.data.product_name
    if (!window.confirm(`Arquivar o contrato “${label}”? Esta ação apenas oculta o contrato vazio da lista ativa. Nenhum lançamento ou dado financeiro será apagado.`)) return
    submitting.current = true; setBusy(true); setWriteError(''); setSuccess('')
    controller.current = new AbortController()
    try {
      await repository.archiveCdb(selected, controller.current.signal)
      if (!active.current) return
      setParams({})
      client.removeQueries({ queryKey: [...prefix, 'detail', selected] })
      client.removeQueries({ queryKey: [...prefix, 'movements', selected] })
      client.removeQueries({ queryKey: [...prefix, 'observations', selected] })
      setSuccess('Contrato vazio arquivado e removido da lista ativa.'); invalidate()
    } catch (error) {
      if (!active.current) return
      if (error instanceof ApiError && [401, 403].includes(error.status)) onAuthError(error)
      else { setWriteError((error as Error).message); invalidate() }
    } finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  async function save(kind: WriteMode, form: FormData) {
    if (submitting.current) return
    submitting.current = true; setBusy(true); setWriteError(''); setSuccess('')
    controller.current = new AbortController()
    const text = (name: string) => String(form.get(name) ?? '')
    try {
      let createdId: number | undefined
      if (kind === 'create') {
        if (text('maturity_date') <= text('application_date')) throw new Error('O vencimento deve ser posterior à data da primeira aplicação.')
        const remuneration = text('remuneration') as CdbInput['remuneration']
        const result = await repository.createCdb({ issuer: text('issuer'), product_name: text('product_name'), product_type: 'CDB', remuneration,
          indexer: remuneration === 'CDI' ? 'CDI' : 'NONE', contracted_rate: text('contracted_rate'), application_date: text('application_date'), maturity_date: text('maturity_date') }, controller.current.signal)
        createdId = result.id
      } else {
        if (!selected || !detail.data) throw new Error('Selecione um CDB antes de movimentar.')
        if (!positive(text('principal_amount'))) throw new Error('O principal deve ser positivo.')
        if (kind === 'application') await repository.applyCdb(selected, { date: text('date'), principal_amount: text('principal_amount') }, controller.current.signal)
        else {
          const lot = detail.data.lots.find(item => item.id === Number(text('lot_id')))
          if (!lot || exceeds(text('principal_amount'), lot.principal_balance)) throw new Error('O principal amortizado supera o saldo disponível do lote.')
          await repository.redeemCdb(selected, { lot_id: lot.id, date: text('date'), principal_amount: text('principal_amount'), cash_received: text('cash_received') === '' ? null : text('cash_received') }, controller.current.signal)
        }
      }
      if (!active.current) return
      setMode(null)
      if (createdId !== undefined) setParams({ investment: String(createdId) })
      setSuccess(kind === 'create' ? 'CDB cadastrado. Registre uma nova aplicação ou inicie com saldo atual.' : kind === 'application' ? 'Aplicação registrada em um novo lote.' : 'Resgate de principal registrado. Confira o histórico atualizado.')
      invalidate() // GET refresh errors are separate from a successful immutable POST.
    } catch (error) {
      if (!active.current) return
      if (error instanceof ApiError && [401, 403].includes(error.status)) { setMode(null); onAuthError(error) }
      else {
        const uncertain = error instanceof TypeError || error instanceof ApiError && error.status >= 500
        setWriteError((error as Error).message + (uncertain ? ' O resultado da gravação pode não estar confirmado. Confira o histórico antes de reenviar; não há reenvio automático.' : ''))
        if (uncertain) invalidate()
      }
    } finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  if (authError) return <section className="fixed-income"><p role="alert">Acesso à renda fixa não autorizado. Verificando sessão…</p></section>
  return <section className="fixed-income" aria-label="Carteira de renda fixa">
    <div className="fi-heading"><div><span className="tag"><Landmark size={14}/> CDB · carteira privada</span><h2>Renda fixa, por contrato e lote</h2><p>Principal conhecido, histórico imutável e estimativas com premissas explícitas.</p></div><Button onClick={() => open('create')}><Plus size={16}/> Cadastrar CDB</Button></div>
    {success && <div className="fi-success" role="status">{success}</div>}
    {list.isPending && <p role="status">Carregando CDBs…</p>}
    {list.isError && <div className="error" role="alert">{(list.error as Error).message}<Button variant="outline" onClick={() => { void list.refetch() }}>Tentar listar novamente</Button></div>}
    {list.data && !list.isError && <article className="panel fi-list">
      <div className="panel-heading"><h3>Seus contratos</h3><span>{list.data.length} nesta página</span></div>
      {!list.data.length ? <div className="empty"><Landmark/><h4>{offset ? 'Nenhum contrato nesta página' : 'Seu primeiro CDB começa aqui'}</h4><p>Cadastre o contrato e escolha: nova aplicação ou saldo atual de um investimento existente.</p><Button variant="outline" onClick={() => open('create')}>Cadastrar primeiro CDB</Button></div> :
        <div className="fi-investment-cards" aria-label="Lista de CDBs">{list.data.map(cdb=><article className="fi-investment-card" key={cdb.id}><small>{cdb.issuer}</small><h3>{cdb.product_name}</h3><p>{contractLabel(cdb)} · Vencimento {dayLabel(cdb.maturity_date)}</p>
          {cdb.latest_observation ? <><span className="tag">Posição informada manualmente · {dayLabel(cdb.latest_observation.as_of)}</span><dl><div><dt>Patrimônio bruto observado</dt><dd>{marketMoney(cdb.latest_observation.gross_value)}</dd></div><div><dt>Disponível líquido observado</dt><dd>{marketMoney(cdb.latest_observation.net_value)}</dd></div></dl><small><span className="fi-value-origin fi-origin-user">Informado pelo usuário</span> Valores da instituição nessa data; não são atualizados automaticamente.</small></> : <p>Nenhuma posição patrimonial informada. Consulte o detalhe para registrar uma aplicação ou iniciar com saldo atual.</p>}
          <Button variant="outline" aria-label={`Abrir ${cdb.product_name}`} onClick={()=>{setParams({investment:String(cdb.id)});setSuccess('')}}>Ver lotes e histórico</Button></article>)}</div>}
      <div className="fi-pagination"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Página anterior</Button><span>Página {offset / 20 + 1}</span><Button variant="outline" disabled={list.data.length < 20} onClick={() => setOffset(value => value + 20)}>Próxima página</Button></div>
    </article>}
    {rawId && !selected && <p role="alert" className="error">Identificador de CDB inválido.</p>}
    {selected && detail.isPending && <p role="status">Carregando posição e lotes…</p>}
    {selected && detail.isError && <div role="alert" className="error">{(detail.error as Error).message}<Button variant="outline" onClick={() => { void detail.refetch() }}>Tentar carregar posição</Button></div>}
    {selected && detail.data && !detail.isError && <div className="fi-detail" aria-label={`Detalhes de ${detail.data.product_name}`}>
      <div className="fi-heading"><div><h2 tabIndex={-1}>{detail.data.product_name}</h2><p>{detail.data.issuer} · {contractLabel(detail.data)} · Vencimento {dayLabel(detail.data.maturity_date)}</p></div><div className="fi-actions">{!detail.data.lots.length&&!detail.data.opening_balance&&!detail.data.latest_observation&&<Button variant="outline" disabled={busy} onClick={()=>void archiveEmptyContract()}>Arquivar contrato</Button>}<Button onClick={() => open('application')}>Nova aplicação</Button><Button variant="outline" disabled={!detail.data.lots.some(lot => positive(lot.principal_balance))} onClick={() => open('redemption')}>Resgatar principal</Button>{detail.data.tracking_mode==='CONSOLIDATED'&&<Button variant="outline" onClick={()=>openManual('observation')}>Registrar nova posição</Button>}<Button variant="outline" onClick={() => setParams({})}>Fechar detalhes</Button></div></div>
      {writeError && <div className="error" role="alert">{writeError}</div>}
      {detail.data.latest_observation&&<ObservedPositionSummary position={detail.data.latest_observation}/>}
      {!detail.data.lots.length&&!detail.data.opening_balance&&<article className="panel fi-section fi-empty-position"><h3>Como deseja começar?</h3><p>Nenhuma aplicação registrada. Não há informação suficiente para apresentar patrimônio ou principal. A primeira aplicação deve ter a data inicial do contrato.</p><div className="fi-actions"><Button onClick={()=>open('application')}>Registrar nova aplicação</Button><Button variant="outline" onClick={()=>openManual('opening')}>Iniciar com saldo atual</Button></div><p><span className="fi-value-origin fi-origin-calculated">Aplicação registrada</span> Cria um lote e registra o principal no ledger. <span className="fi-value-origin fi-origin-user">Posição observada</span> Registra o saldo declarado do CDB inteiro, sem inventar aplicações históricas; valor não é somado ao principal dos lotes.</p></article>}
      {detail.data.lots.length>0&&<div className="fi-metrics"><article className="metric"><span>{detail.data.tracking_mode==='CONSOLIDATED'?'Aplicações dos novos lotes':'Principal aplicado acumulado'} <FinancialHint label="principal aplicado acumulado">Soma das aplicações registradas no histórico completo. Em CDB com posição observada, considera apenas os lotes criados depois dela; a posição observada do CDB inteiro não é incluída.</FinancialHint></span><h2>{marketMoney(completeHistory ? totalApplications(rows) : null)}</h2><small><span className="fi-value-origin fi-origin-calculated">Calculado do ledger</span> {completeHistory ? 'Soma das aplicações registradas; exclui a posição manual' : 'Depende de carregar o histórico completo'}</small></article><article className="metric"><span>{detail.data.tracking_mode==='CONSOLIDATED'?'Principal remanescente dos novos lotes':'Principal remanescente atual'} <FinancialHint label="principal remanescente">Principal ainda não amortizado dos lotes registrados, sem rendimentos nem posição observada.</FinancialHint></span><h2>{marketMoney(detail.data.principal_balance)}</h2><small><span className="fi-value-origin fi-origin-calculated">Calculado do ledger</span> Somente saldo do ledger. Não somar ao patrimônio observado do CDB inteiro.</small></article></div>}
      <article className="panel fi-section"><h3>Lotes da posição <FinancialHint label="lotes">Cada aplicação cria um lote próprio para acompanhar principal e prazo. Um saldo inicial observado não cria lote nem aplicação histórica.</FinancialHint></h3>{!detail.data.lots.length ? <p>Nenhuma aplicação registrada. A primeira deve ter a data inicial do contrato.</p> : <div className="table-scroll" tabIndex={0} role="region" aria-label="Lotes de renda fixa"><table><thead><tr><th scope="col">Lote</th><th scope="col">Aplicação</th><th scope="col">Principal remanescente <FinancialHint label="principal remanescente por lote">Aplicações menos amortizações daquele lote; o rendimento estimado é apresentado separadamente.</FinancialHint></th><th scope="col">Situação</th></tr></thead><tbody>{detail.data.lots.map(lot => <tr key={lot.id}><th scope="row">{lot.id}</th><td>{dayLabel(lot.application_date)}</td><td title={lot.principal_balance}>{marketMoney(lot.principal_balance)}</td><td>{positive(lot.principal_balance) ? 'Com principal' : 'Encerrado · histórico preservado'}</td></tr>)}</tbody></table></div>}</article>
      <article className="panel fi-section"><h3>Histórico de movimentações <FinancialHint label="histórico de movimentações">Registro de aplicações e amortizações por lote. O caixa recebido no resgate pode incluir rendimento ou tributos e não é, por si só, lucro.</FinancialHint></h3><p><span className="fi-value-origin fi-origin-calculated">Movimentações registradas</span> Movimentos originais, sem edição ou exclusão. Valores apresentados em centavos; registros preservam até oito casas.</p>
        {history.isPending && <p role="status">Carregando movimentações…</p>}
        {history.isError && <div className="error" role="alert">{(history.error as Error).message}<Button variant="outline" onClick={() => { void history.refetch() }}>Tentar carregar histórico</Button></div>}
        {!history.isError && history.data && (!rows.length ? <p>Nenhuma movimentação registrada.</p> : <div className="table-scroll" role="region" aria-label="Histórico de CDB" tabIndex={0}><table><thead><tr>{['Data', 'Movimento', 'Lote', 'Principal', 'Caixa recebido', 'Revisões e ações'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{dayLabel(row.date)}</td><td><span className="operation-tag">{row.kind === 'APPLICATION' ? 'Aplicação' : 'Resgate'}</span></td><td>{row.lot_id}</td><td title={row.principal_amount}>{marketMoney(row.principal_amount)}</td><td>{row.kind === 'APPLICATION' ? 'Não se aplica' : row.cash_received == null ? 'Não informado' : marketMoney(row.cash_received)}</td><td>{row.kind === 'APPLICATION' ? <ApplicationRevisionHistory investmentId={selected} movement={row} identity={identity} repository={repository} onRevise={(movement, kind) => { focus.current = document.activeElement as HTMLElement; setRevisionTarget({ movement, kind }) }}/> : '—'}</td></tr>)}</tbody></table></div>)}
        {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => { void history.fetchNextPage() }}>{history.isFetchingNextPage ? 'Carregando…' : 'Carregar mais movimentações'}</Button>}
        <p className="fi-notice">Caixa de resgate não é rendimento. Resultado realizado, IR e IOF efetivamente retidos não são apurados pelos dados atuais.</p>
      </article>
      <article className="panel fi-section"><h3>Auditoria das aplicações originais</h3><p>Esta lista vem do ledger original. Aplicações anuladas continuam visíveis aqui; a projeção efetiva e os cálculos permanecem separados.</p>
        {originalHistory.isPending && <p role="status">Carregando aplicações originais…</p>}
        {originalHistory.isError && <div className="error" role="alert">{(originalHistory.error as Error).message}<Button variant="outline" onClick={()=>{void originalHistory.refetch()}}>Tentar carregar aplicações originais</Button></div>}
        {!originalHistory.isError && originalHistory.data && <div className="fi-original-applications">{originalRows.filter(row=>row.kind==='APPLICATION').map(row=><section className="fi-original-application" key={row.id}>
          <h4>Aplicação original #{row.id} · Lote #{row.lot_id}</h4><p>{marketMoney(row.principal_amount)} em {dayLabel(row.date)} · O registro original não é editável.</p>
          <ApplicationRevisionHistory investmentId={selected} movement={row} identity={identity} repository={repository}/>
        </section>)}</div>}
        {originalHistory.hasNextPage && <Button variant="outline" disabled={originalHistory.isFetchingNextPage} onClick={()=>{void originalHistory.fetchNextPage()}}>{originalHistory.isFetchingNextPage?'Carregando…':'Carregar mais aplicações originais'}</Button>}
      </article>
      <FixedIncomeReturns key={`${selected}-${epoch}`} detail={detail.data} repository={repository} identity={identity} onAuthError={onAuthError}/>
      {detail.data.tracking_mode==='CONSOLIDATED'&&<article className="panel fi-section"><h3>Conciliação manual e posições anteriores</h3><p>Após resgatar capital antigo sem lotes, registre uma nova observação do CDB inteiro com motivo “Conciliação após resgate”. Não use o formulário de amortização dos novos lotes.</p><Button variant="outline" onClick={()=>openManual('observation')}>Conciliar posição manualmente</Button>{observations.isPending&&<p role="status">Carregando observações…</p>}{observations.isError&&<div className="error" role="alert">{(observations.error as Error).message}<Button onClick={()=>{void observations.refetch()}}>Tentar carregar posições</Button></div>}
        {observations.data&&<details><summary>Ver todas as posições preservadas</summary>{observations.data.pages.flat().map(row=><section key={row.id}><h4>{dayLabel(row.as_of)} · {row.kind==='OPENING'?'Abertura':'Observação'}</h4><p>{row.source} · Bruto {marketMoney(row.gross_value)} · Líquido {marketMoney(row.net_value)} · {row.confirmed_principal===null?'Principal não informado':`Principal confirmado ${marketMoney(row.confirmed_principal)}`}</p>{row.reason==='AFTER_CONSOLIDATED_REDEMPTION'&&<p>Caixa recebido informado: {marketMoney(row.cash_received)}. Não representa lucro apurado.</p>}</section>)}</details>}{observations.hasNextPage&&<Button onClick={()=>{void observations.fetchNextPage()}}>Carregar mais posições</Button>}</article>}
    </div>}
    <FixedIncomeDialog mode={mode} setMode={setMode} cdbs={list.data ?? []} selected={selected} select={id => setParams({ investment: String(id) })} detail={!detail.isError ? detail.data : undefined} busy={busy} error={writeError} onSave={(kind, form) => { void save(kind, form) }} returnFocus={focus.current}/>
    {manualMode&&detail.data&&!detail.isError&&<ManualPositionDialog detail={detail.data} opening={manualMode==='opening'} busy={busy} error={writeError} close={()=>setManualMode(null)} save={data=>{void saveManual(data)}} returnFocus={focus.current}/>}
    {revisionTarget && selected !== null && <ApplicationRevisionDialog investmentId={selected} movement={revisionTarget.movement} kind={revisionTarget.kind} repository={repository}
      onClose={()=>setRevisionTarget(null)} returnFocus={focus.current} onAuthError={onAuthError} onConflict={invalidate}
      onSuccess={()=>{focus.current=document.querySelector('.fi-detail h2');setRevisionTarget(null);setSuccess(revisionTarget.kind==='REPLACE'?'Aplicação corrigida na projeção efetiva. O registro original foi preservado.':'Aplicação anulada contabilmente. Nenhum resgate ou caixa fictício foi criado.');invalidate()}}/>}
  </section>
}
