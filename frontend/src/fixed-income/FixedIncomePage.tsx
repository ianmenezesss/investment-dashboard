import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Landmark, Plus } from 'lucide-react'
import { ApiError } from '../api'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import { Button } from '../components/ui/button'
import { marketMoney } from '../components/market-format'
import { FixedIncomeDialog, type DialogMode, type WriteMode } from './FixedIncomeDialog'
import { FixedIncomeReturns } from './FixedIncomeReturns'
import { contractLabel, dayLabel, exceeds, positive, totalApplications } from './format'
import type { CdbInput } from './types'
import './fixed-income.css'

export function FixedIncomePage({ repository, identity, newOperationRequest, onAuthError }: {
  repository: PrivateRepository; identity: string; newOperationRequest: number; onAuthError: (error: ApiError) => void
}) {
  const [params, setParams] = useSearchParams()
  const rawId = params.get('investment')
  const selected = rawId && /^[1-9]\d*$/.test(rawId) && Number.isSafeInteger(Number(rawId)) ? Number(rawId) : null
  const [offset, setOffset] = useState(0)
  const [mode, setMode] = useState<DialogMode>(null)
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
  const errors = [list.error, detail.error, history.error]
  const authError = errors.find(error => error instanceof ApiError && error.status === 401) || errors.find(error => error instanceof ApiError && error.status === 403)
  useEffect(() => { if (authError instanceof ApiError) onAuthError(authError) }, [authError, onAuthError])
  const rows = history.data?.pages.flat() ?? []
  const completeHistory = !!history.data && !history.hasNextPage && !history.isError
  function invalidate() {
    setEpoch(value => value + 1)
    client.removeQueries({ queryKey: [...prefix, 'returns'] })
    void client.invalidateQueries({ queryKey: prefix })
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
      setSuccess(kind === 'create' ? 'CDB cadastrado. Registre a primeira aplicação para movimentar principal.' : kind === 'application' ? 'Aplicação registrada em um novo lote.' : 'Resgate de principal registrado. Confira o histórico atualizado.')
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
      {!list.data.length ? <div className="empty"><Landmark/><h4>{offset ? 'Nenhum contrato nesta página' : 'Seu primeiro CDB começa aqui'}</h4><p>Cadastre os termos do produto; depois registre a aplicação real.</p><Button variant="outline" onClick={() => open('create')}>Cadastrar primeiro CDB</Button></div> :
        <div className="table-scroll" role="region" aria-label="Lista de CDBs" tabIndex={0}><table><caption className="sr-only">Contratos de renda fixa da conta conectada</caption><thead><tr>{['Instituição e produto', 'Remuneração contratada', 'Aplicação inicial', 'Vencimento', 'Detalhes'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{list.data.map(cdb => <tr key={cdb.id}>
          <th scope="row">{cdb.product_name}<small>{cdb.issuer}</small></th><td>{contractLabel(cdb)}</td><td>{dayLabel(cdb.application_date)}</td><td>{dayLabel(cdb.maturity_date)}</td><td><Button variant="outline" aria-label={`Abrir ${cdb.product_name}`} onClick={() => { setParams({ investment: String(cdb.id) }); setSuccess('') }}>Ver lotes e histórico</Button></td></tr>)}</tbody></table></div>}
      <div className="fi-pagination"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Página anterior</Button><span>Página {offset / 20 + 1}</span><Button variant="outline" disabled={list.data.length < 20} onClick={() => setOffset(value => value + 20)}>Próxima página</Button></div>
    </article>}
    {rawId && !selected && <p role="alert" className="error">Identificador de CDB inválido.</p>}
    {selected && detail.isPending && <p role="status">Carregando posição e lotes…</p>}
    {selected && detail.isError && <div role="alert" className="error">{(detail.error as Error).message}<Button variant="outline" onClick={() => { void detail.refetch() }}>Tentar carregar posição</Button></div>}
    {selected && detail.data && !detail.isError && <div className="fi-detail" aria-label={`Detalhes de ${detail.data.product_name}`}>
      <div className="fi-heading"><div><h2>{detail.data.product_name}</h2><p>{detail.data.issuer} · {contractLabel(detail.data)} · {dayLabel(detail.data.application_date)} a {dayLabel(detail.data.maturity_date)}</p></div><div className="fi-actions"><Button onClick={() => open('application')}>Nova aplicação</Button><Button variant="outline" disabled={!detail.data.lots.some(lot => positive(lot.principal_balance))} onClick={() => open('redemption')}>Resgatar principal</Button><Button variant="outline" onClick={() => setParams({})}>Fechar detalhes</Button></div></div>
      <div className="fi-metrics"><article className="metric"><span>Principal aplicado acumulado</span><h2>{marketMoney(completeHistory ? totalApplications(rows) : null)}</h2><small>{completeHistory ? 'Soma das aplicações; não é saldo atual nem rendimento' : 'Depende de carregar o histórico completo'}</small></article><article className="metric"><span>Principal remanescente atual</span><h2>{marketMoney(detail.data.principal_balance)}</h2><small>Saldo contábil informado pela API, sem rendimentos</small></article></div>
      <article className="panel fi-section"><h3>Lotes da posição</h3>{!detail.data.lots.length ? <p>Nenhuma aplicação registrada. A primeira deve ter a data inicial do contrato.</p> : <div className="table-scroll" tabIndex={0} role="region" aria-label="Lotes de renda fixa"><table><thead><tr><th scope="col">Lote</th><th scope="col">Aplicação</th><th scope="col">Principal remanescente</th><th scope="col">Situação</th></tr></thead><tbody>{detail.data.lots.map(lot => <tr key={lot.id}><th scope="row">{lot.id}</th><td>{dayLabel(lot.application_date)}</td><td title={lot.principal_balance}>{marketMoney(lot.principal_balance)}</td><td>{positive(lot.principal_balance) ? 'Com principal' : 'Encerrado · histórico preservado'}</td></tr>)}</tbody></table></div>}</article>
      <article className="panel fi-section"><h3>Histórico de movimentações</h3><p>Movimentos originais, sem edição ou exclusão. Valores apresentados em centavos; registros preservam até oito casas.</p>
        {history.isPending && <p role="status">Carregando movimentações…</p>}
        {history.isError && <div className="error" role="alert">{(history.error as Error).message}<Button variant="outline" onClick={() => { void history.refetch() }}>Tentar carregar histórico</Button></div>}
        {!history.isError && history.data && (!rows.length ? <p>Nenhuma movimentação registrada.</p> : <div className="table-scroll" role="region" aria-label="Histórico de CDB" tabIndex={0}><table><thead><tr>{['Data', 'Movimento', 'Lote', 'Principal', 'Caixa recebido'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{dayLabel(row.date)}</td><td><span className="operation-tag">{row.kind === 'APPLICATION' ? 'Aplicação' : 'Resgate'}</span></td><td>{row.lot_id}</td><td title={row.principal_amount}>{marketMoney(row.principal_amount)}</td><td>{row.kind === 'APPLICATION' ? 'Não se aplica' : row.cash_received == null ? 'Não informado' : marketMoney(row.cash_received)}</td></tr>)}</tbody></table></div>)}
        {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => { void history.fetchNextPage() }}>{history.isFetchingNextPage ? 'Carregando…' : 'Carregar mais movimentações'}</Button>}
        <p className="fi-notice">Caixa de resgate não é rendimento. Resultado realizado, IR e IOF efetivamente retidos não são apurados pelos dados atuais.</p>
      </article>
      <FixedIncomeReturns key={`${selected}-${epoch}`} detail={detail.data} repository={repository} identity={identity} onAuthError={onAuthError}/>
    </div>}
    <FixedIncomeDialog mode={mode} setMode={setMode} cdbs={list.data ?? []} selected={selected} select={id => setParams({ investment: String(id) })} detail={!detail.isError ? detail.data : undefined} busy={busy} error={writeError} onSave={(kind, form) => { void save(kind, form) }} returnFocus={focus.current}/>
  </section>
}
