import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Button } from '../components/ui/button'
import type { PrivateRepository } from '../repositories/PrivateRepository'
import type { CdbMovement } from './types'
import type { RevisionKind } from './ApplicationRevisionDialog'
import { dayLabel } from './format'
import { marketMoney } from '../components/market-format'

export function ApplicationRevisionHistory({ investmentId, movement, identity, repository, onRevise }: {
  investmentId: number; movement: CdbMovement; identity: string; repository: PrivateRepository
  onRevise?: (movement: CdbMovement, kind: RevisionKind) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const history = useInfiniteQuery({
    queryKey: ['fixed-income', identity, 'application-revisions', investmentId, movement.id],
    initialPageParam: 0,
    queryFn: ({ signal, pageParam }) => repository.cdbApplicationRevisions(investmentId, movement.id, pageParam, signal),
    enabled: expanded,
    getNextPageParam: (last, _pages, offset) => last.length === 100 ? offset + 100 : undefined,
    retry: false, staleTime: 0, refetchOnWindowFocus: false,
  })
  const revisions = history.data?.pages.flat() ?? []
  return <div className="fi-revision-actions">
    {onRevise && <div className="fi-actions">
      <Button variant="outline" onClick={() => onRevise(movement, 'REPLACE')}>Corrigir aplicação</Button>
      <Button variant="outline" onClick={() => onRevise(movement, 'VOID')}>Anular aplicação</Button>
    </div>}
    <button type="button" className="fi-history-toggle" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      {expanded ? 'Ocultar revisões' : 'Ver histórico de revisões'}
    </button>
    {expanded && <div className="fi-revision-history" aria-label={`Revisões da aplicação ${movement.id}`}>
      <p>Eventos de auditoria imutáveis. O lançamento original continua preservado.</p>
      {history.isPending && <p role="status">Carregando revisões…</p>}
      {history.isError && <div role="alert" className="error">{(history.error as Error).message}<Button variant="outline" onClick={() => { void history.refetch() }}>Tentar carregar revisões</Button></div>}
      {!history.isError && history.data && (revisions.length ? <ol>
        {revisions.map(revision => <li key={revision.id}>
          <strong>#{revision.revision} · {revision.kind === 'REPLACE' ? 'Correção' : 'Anulação contábil'}</strong>
          <span>{revision.kind === 'REPLACE' ? `${marketMoney(revision.replacement_amount ?? '0')} · ${revision.replacement_date ? dayLabel(revision.replacement_date) : 'Data não informada'}` : 'Sem substituição de valor/data; nenhum resgate criado'}</span>
          <span>Motivo: {revision.reason}</span>
          <time dateTime={revision.created_at}>Registrada em {new Date(revision.created_at).toLocaleString('pt-BR')}</time>
        </li>)}
      </ol> : <p>Nenhuma revisão registrada.</p>)}
      {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => { void history.fetchNextPage() }}>
        {history.isFetchingNextPage ? 'Carregando…' : 'Carregar mais revisões'}
      </Button>}
    </div>}
  </div>
}
