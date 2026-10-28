export type CdbInput = {
  issuer: string; product_name: string; product_type: 'CDB'; remuneration: 'FIXED' | 'CDI'
  indexer: 'NONE' | 'CDI'; contracted_rate: string; application_date: string; maturity_date: string
}
export type Cdb = CdbInput & { id: number; created_at: string }
export type CdbLot = { id: number; application_date: string; principal_balance: string }
export type CdbDetail = Cdb & { principal_balance: string; lots: CdbLot[] }
export type ApplicationInput = { date: string; principal_amount: string }
export type RedemptionInput = ApplicationInput & { lot_id: number; cash_received: string | null }
export type CdbMovement = ApplicationInput & {
  id: number; investment_id: number; lot_id: number; kind: 'APPLICATION' | 'REDEMPTION'
  cash_received: string | null; created_at: string
}
export type ReturnsInput = {
  as_of: string; convention: 'daily_cdi_pro_rata_decimal_v1'; calendar: 'anbima_2024_2026_v1'; tax_profile: 'br_resident_individual'
}
export type ReturnAmounts = {
  principal_balance: string; gross_income_estimate: string | null; gross_value_estimate: string | null
  ir_estimate: string | null; iof_estimate: string | null; net_income_estimate: string | null; net_value_estimate: string | null
}
export type CdbLotReturns = ReturnAmounts & {
  lot_id: number; application_date: string; accrual_end_exclusive: string; tax_basis_date: string; calendar_days: number
  status: 'estimated' | 'closed' | 'convention_required' | 'calendar_required' | 'unsupported_calendar' | 'unsupported_product' |
    'incomplete_history' | 'invalid_rates' | 'rates_unavailable' | 'tax_profile_required' | 'matured_unsettled'
  missing_rate_dates: string[]; applied_rate_count: number; factor: string | null; ir_rate_percent: string | null; iof_rate_percent: string | null
  realized_tax_status: 'not_applicable' | 'insufficient_information'; realized_ir: string | null; realized_iof: string | null; realized_income: string | null
}
export type CdbReturns = ReturnAmounts & {
  investment_id: number; as_of: string; ledger_as_of: string; convention: ReturnsInput['convention'] | null
  calendar: ReturnsInput['calendar'] | null; tax_profile: ReturnsInput['tax_profile'] | null; model_version: '2.0.3'; currency: 'BRL'; source: 'BCB/SGS 12'
  status: 'estimated' | 'incomplete' | 'empty'; rates_error: string | null; warnings: string[]; lots: CdbLotReturns[]
  rates_references: { start_date: string; end_date: string; fetched_at: string; expires_at: string; from_cache: boolean }[]
}
