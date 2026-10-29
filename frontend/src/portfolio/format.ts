const brlAxis = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 2, minimumFractionDigits: 0 })
const compactAxis = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 8 })

/** Keep small values legible and preserve enough precision to avoid duplicate abbreviated ticks. */
export function formatFlowAxisTick(value: number): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return 'Indisponível'
  if (Math.abs(amount) < 1000) return brlAxis.format(amount)
  return `R$ ${compactAxis.format(amount / 1000)} mil`
}
