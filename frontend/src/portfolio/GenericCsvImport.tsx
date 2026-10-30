import { useMemo, useState } from 'react'
import type { FinancialEventInput, FinancialEventKind, FinancialEventRecord } from '../repositories/PrivateRepository'

type ImportResult = { imported_count: number; duplicate_count: number }
type Repo = {
  financialEvents: () => Promise<FinancialEventRecord[]>
  importFinancialEvents: (rows: Array<{ row_number: number; event: FinancialEventInput }>, key: string) => Promise<ImportResult>
}
const fields = ['event_date', 'kind', 'cash_amount', 'ticker'] as const
const mappingFields = [...fields, 'source'] as const
type Field = typeof mappingFields[number]
type Preview = { row: number; event: FinancialEventInput; valid: boolean; duplicate: boolean; error: string }

export function parseGenericCsv(text: string): string[][] {
  text = text.replace(/^\uFEFF/, '')
  const sample = text.replace(/^\uFEFF/, '').slice(0, 8192)
  let delimiter = ','
  let best = -1
  for (const candidate of [',', ';', '\t']) {
    let count = 0, quoted = false
    for (const char of sample) {
      if (char === '"') quoted = !quoted
      else if (!quoted && (char === '\n' || char === '\r')) break
      else if (!quoted && char === candidate) count++
    }
    if (count > best) { best = count; delimiter = candidate }
  }
  const matrix: string[][] = []
  let row: string[] = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { cell += '"'; i++ }
      else if (char === '"') quoted = false
      else cell += char
    } else if (char === '"') {
      if (cell.trim()) throw new Error('Aspas só podem iniciar uma célula CSV')
      cell = ''; quoted = true
    } else if (char === delimiter) { row.push(cell); cell = '' }
    else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++
      row.push(cell); cell = ''
      if (row.some(value => value.trim())) matrix.push(row)
      row = []
    } else cell += char
  }
  if (quoted) throw new Error('CSV contém aspas sem fechamento')
  if (cell.length || row.length) { row.push(cell); if (row.some(value => value.trim())) matrix.push(row) }
  if (matrix.length < 2) throw new Error('CSV precisa ter cabeçalho e ao menos uma linha')
  if (matrix.length > 501) throw new Error('Importe no máximo 500 linhas por lote')
  const width = matrix[0].length
  if (!width || matrix.some(values => values.length !== width)) throw new Error('CSV contém linhas com quantidade irregular de colunas')
  if (matrix[0].some(value => !value.trim()) || new Set(matrix[0].map(value => value.trim().toLocaleLowerCase('pt-BR'))).size !== width)
    throw new Error('Cabeçalhos vazios ou repetidos não podem ser mapeados com segurança')
  return matrix
}

function decodeCsv(buffer: ArrayBuffer): string {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buffer) }
  catch { try { return new TextDecoder('windows-1252', { fatal: true }).decode(buffer) }
    catch { throw new Error('Codificação não suportada. Use UTF-8 ou Windows-1252.') } }
}

function normalizeDate(value: string): string | null {
  let year: number, month: number, day: number
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim())
  const br = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value.trim())
  if (iso) { year = Number(iso[1]); month = Number(iso[2]); day = Number(iso[3]) }
  else if (br) { day = Number(br[1]); month = Number(br[2]); year = Number(br[3]) }
  else return null
  const date = new Date(Date.UTC(year!, month! - 1, day!))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month! - 1 && date.getUTCDate() === day ? `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}` : null
}

function normalizeMoney(value: string): string | null {
  let raw = value.trim().replace(/\s/g, '').replace(/^R\$/i, '')
  if (!raw || /[^\d.,+-]/.test(raw) || raw.startsWith('-') || raw.startsWith('+')) return null
  const comma = raw.lastIndexOf(','), dot = raw.lastIndexOf('.')
  if (comma >= 0 && dot >= 0) raw = comma > dot ? raw.replace(/\./g, '').replace(',', '.') : raw.replace(/,/g, '')
  else if (comma >= 0) raw = raw.replace(',', '.')
  if (!/^\d+(?:\.\d{1,8})?$/.test(raw)) return null
  const [whole, fraction = ''] = raw.split('.')
  const canonical = `${whole.replace(/^0+(?=\d)/, '')}.${fraction}`
  if (whole.replace(/^0+(?=\d)/, '').length > 12 || canonical.length > 21 || !/[1-9]/.test(canonical)) return null
  return canonical
}

function moneyKey(value: string | null | undefined) {
  if (!value) return ''
  const [whole, fraction = ''] = value.split('.')
  return `${whole.replace(/^0+(?=\d)/, '')}.${fraction.replace(/0+$/, '')}`
}
function eventKey(event: Pick<FinancialEventInput, 'kind'|'event_date'|'ticker'|'cash_amount'|'gross_amount'|'tax_withheld'|'description'>) {
  return [event.kind, event.event_date, event.ticker?.toUpperCase() ?? '', moneyKey(event.cash_amount)].join('|')
}
function idempotencyKey() {
  if (!globalThis.crypto?.randomUUID) throw new Error('Este navegador não oferece identificador seguro; atualize-o antes de importar.')
  return globalThis.crypto.randomUUID()
}

export function GenericCsvImport({ repository, onDone }: { repository: Repo; onDone?: () => void }) {
  const [headers, setHeaders] = useState<string[]>([]), [rows, setRows] = useState<string[][]>([])
  const [mapping, setMapping] = useState<Record<Field, number | ''>>({ event_date: '', kind: '', cash_amount: '', ticker: '', source: '' })
  const [existing, setExisting] = useState<FinancialEventRecord[]>([]), [batchKey, setBatchKey] = useState('')
  const [sourceLabel, setSourceLabel] = useState('')
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [confirmed, setConfirmed] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)

  const preview = useMemo<Preview[]>(() => {
    const seen = new Set<string>()
    const persisted = new Set(existing.map(eventKey))
    return rows.map((row, index) => {
      const value = (field: Field) => mapping[field] === '' ? '' : (row[mapping[field]] ?? '').trim()
      const date = normalizeDate(value('event_date'))
      const kind = value('kind').toUpperCase() as FinancialEventKind
      const amount = normalizeMoney(value('cash_amount'))
      const ticker = value('ticker').toUpperCase() || null
      const source = mapping.source === '' ? sourceLabel.trim() : (row[mapping.source] ?? '').trim() || sourceLabel.trim()
      const validKind = ['CONTRIBUTION', 'WITHDRAWAL', 'DIVIDEND', 'JCP'].includes(kind)
      const needsTicker = kind === 'DIVIDEND' || kind === 'JCP'
      let message = ''
      if (fields.some(field => mapping[field] === '')) message = 'Mapeie todas as colunas obrigatórias'
      else if (!date) message = 'Data inválida; use AAAA-MM-DD ou DD/MM/AAAA'
      else if (!validKind) message = 'Tipo inválido; use CONTRIBUTION, WITHDRAWAL, DIVIDEND ou JCP'
      else if (!amount) message = 'Valor inválido; use até 8 casas decimais e valor positivo'
      else if (needsTicker ? !ticker || !/^[A-Z0-9]{4,20}$/.test(ticker) : !!ticker) message = needsTicker ? 'Informe um ticker válido' : 'Aporte e retirada não aceitam ticker'
      else if (!source || source.length > 240) message = 'Informe a origem do registro com até 240 caracteres'
      const event: FinancialEventInput = {
        kind: validKind ? kind : 'CONTRIBUTION', event_date: date ?? '',
        cash_amount: amount ?? '', ticker: needsTicker ? ticker : null,
        gross_amount: null, tax_withheld: null, source, description: null,
      }
      const key = eventKey(event)
      const duplicate = !message && (persisted.has(key) || seen.has(key))
      if (!message) seen.add(key)
      return { row: index + 2, event, valid: !message, duplicate, error: message || (duplicate ? 'Possível duplicata; não será gravada' : '') }
    })
  }, [rows, mapping, existing])

  async function load(file?: File) {
    setError(''); setConfirmed(false); setResult(null)
    if (!file) return
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('O arquivo deve ter no máximo 5 MB')
      const matrix = parseGenericCsv(decodeCsv(await file.arrayBuffer()))
      const columns = matrix[0].map(value => value.trim())
      const current = await repository.financialEvents()
      setHeaders(columns); setRows(matrix.slice(1)); setExisting(current); setMapping({ event_date: '', kind: '', cash_amount: '', ticker: '', source: '' }); setBatchKey(idempotencyKey())
    } catch (cause) { setHeaders([]); setRows([]); setBatchKey(''); setError(cause instanceof Error ? cause.message : 'Não foi possível preparar o CSV') }
  }
  async function importRows() {
    setBusy(true); setError('')
    try {
      const validRows = preview.filter(item => item.valid && !item.duplicate).map(({ row, event }) => ({ row_number: row, event }))
      const response = await repository.importFinancialEvents(validRows, batchKey)
      setResult(response); setConfirmed(false); onDone?.()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Falha na importação. Você pode reenviar o mesmo lote com segurança.') }
    finally { setBusy(false) }
  }
  function cancel() {
    setHeaders([]); setRows([]); setExisting([]); setBatchKey(''); setConfirmed(false); setResult(null); setError('')
  }

  return <section className="panel csv-import" aria-label="Importação CSV genérica">
    <h2>Importar eventos de CSV</h2>
    <p>O arquivo é processado localmente. A prévia não grava dados. Este fluxo importa aportes, retiradas, dividendos e JCP com layout mapeado por você.</p>
    <label>Arquivo CSV<input aria-label="Selecionar arquivo CSV" type="file" accept=".csv,text/csv" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; void load(file) }}/></label>
    {error && <p role="alert">{error}</p>}
    {headers.length > 0 && <>
      <label>Origem do registro<input aria-label="Origem do registro" value={sourceLabel} maxLength={240} placeholder="Extrato, informe ou documento consultado" onChange={event => {
        setSourceLabel(event.target.value); setConfirmed(false); setResult(null)
        try { setBatchKey(idempotencyKey()); setError('') } catch (cause) { setError(cause instanceof Error ? cause.message : 'Identificador seguro indisponível') }
      }}/></label>
      <div className="csv-mapping">{mappingFields.map(field => <label key={field}>{field === 'event_date' ? 'Data' : field === 'kind' ? 'Tipo' : field === 'cash_amount' ? 'Valor recebido' : field === 'ticker' ? 'Ticker' : 'Origem no CSV (opcional)'}<select aria-label={`Mapear ${field}`} value={mapping[field]} onChange={event => {
        setMapping({ ...mapping, [field]: event.target.value === '' ? '' : Number(event.target.value) }); setConfirmed(false); setResult(null)
        try { setBatchKey(idempotencyKey()); setError('') } catch (cause) { setError(cause instanceof Error ? cause.message : 'Identificador seguro indisponível') }
      }}><option value="">Não mapear; usar origem informada</option>{headers.map((header, index) => <option key={index} value={index}>{header}</option>)}</select></label>)}</div>
      <p role="status">{preview.length} linhas: {preview.filter(item => item.valid && !item.duplicate).length} válidas, {preview.filter(item => !item.valid).length} inválidas, {preview.filter(item => item.duplicate).length} possíveis duplicatas.</p>
      <div className="table-scroll"><table><thead><tr><th>Linha</th><th>Data</th><th>Tipo</th><th>Valor</th><th>Ticker</th><th>Resultado</th></tr></thead><tbody>{preview.map(item => <tr key={item.row}><td>{item.row}</td><td>{item.event.event_date || '—'}</td><td>{item.event.kind}</td><td>{item.event.cash_amount || '—'}</td><td>{item.event.ticker || '—'}</td><td>{item.error || 'Pronta'}</td></tr>)}</tbody></table></div>
      <label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/> Confirmo importar as linhas válidas e não duplicadas</label>
      <button disabled={!confirmed || busy || result !== null || !preview.some(item => item.valid && !item.duplicate)} onClick={() => void importRows()}>{busy ? 'Importando lote…' : 'Importar lote confirmado'}</button>
      <button type="button" disabled={busy} onClick={cancel}>Cancelar</button>
      {result && <p role="status">Importação concluída: {result.imported_count} importadas e {result.duplicate_count} duplicadas ignoradas. Linhas inválidas não foram enviadas.</p>}
    </>}
  </section>
}
