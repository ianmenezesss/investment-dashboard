import Decimal from 'decimal.js'

// Presentation only: keep backend decimal strings exact until final rounding.
function localized(value: string | null | undefined, places: number): string | null {
  if (value == null) return null
  try {
    const n = new Decimal(value)
    if (!n.isFinite()) return null
    const [whole, fraction] = n.toFixed(places, Decimal.ROUND_HALF_EVEN).split('.')
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (fraction ? ',' + fraction : '')
  } catch { return null }
}
export function marketMoney(value: string | null | undefined) {
  const text = localized(value, 2)
  return text == null ? 'Indisponível' : text.startsWith('-') ? '-R$ ' + text.slice(1) : 'R$ ' + text
}
export function marketPercent(value: string | null | undefined) {
  const text = localized(value, 2)
  return text == null ? 'Indisponível' : text + '%'
}
export function marketQuantity(value: string) {
  return localized(value, 8)?.replace(/(,\d*?[1-9])0+$|,0+$/, '$1') ?? '—'
}
export function marketTone(value: string | null | undefined) {
  if (value == null) return 'muted'
  try { return new Decimal(value).lt(0) ? 'negative' : 'positive' } catch { return 'muted' }
}
