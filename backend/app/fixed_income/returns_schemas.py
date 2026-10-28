from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel
from .schemas import InvestmentOutput, MovementOutput

Convention = Literal["daily_cdi_pro_rata_decimal_v1"]
Calendar = Literal["anbima_2024_2026_v1"]
TaxProfile = Literal["br_resident_individual"]


@dataclass(frozen=True)
class LotSnapshot:
    id: int
    application_date: date


@dataclass(frozen=True)
class ReturnsSnapshot:
    contract: InvestmentOutput
    lots: tuple[LotSnapshot, ...]
    movements: tuple[MovementOutput, ...]
    ledger_as_of: datetime


class LotReturns(BaseModel):
    lot_id: int
    application_date: date
    accrual_end_exclusive: date
    tax_basis_date: date
    calendar_days: int
    principal_balance: Decimal
    status: Literal["estimated", "closed", "convention_required", "calendar_required", "unsupported_calendar",
                    "unsupported_product", "incomplete_history", "invalid_rates", "rates_unavailable", "tax_profile_required", "matured_unsettled"]
    missing_rate_dates: list[date] = []
    applied_rate_count: int = 0
    factor: Decimal | None = None
    gross_income_estimate: Decimal | None = None
    gross_value_estimate: Decimal | None = None
    ir_rate_percent: Decimal | None = None
    iof_rate_percent: Decimal | None = None
    ir_estimate: Decimal | None = None
    iof_estimate: Decimal | None = None
    net_income_estimate: Decimal | None = None
    net_value_estimate: Decimal | None = None
    realized_tax_status: Literal["not_applicable", "insufficient_information"]
    realized_ir: Decimal | None = None
    realized_iof: Decimal | None = None
    realized_income: Decimal | None = None


class RatesReference(BaseModel):
    start_date: date
    end_date: date
    fetched_at: datetime
    expires_at: datetime
    from_cache: bool


class InvestmentReturns(BaseModel):
    investment_id: int
    as_of: date
    ledger_as_of: datetime
    convention: Convention | None
    calendar: Calendar | None
    tax_profile: TaxProfile | None
    model_version: Literal["2.0.3"] = "2.0.3"
    currency: Literal["BRL"] = "BRL"
    source: Literal["BCB/SGS 12"] = "BCB/SGS 12"
    status: Literal["estimated", "incomplete", "empty"]
    principal_balance: Decimal
    gross_income_estimate: Decimal | None
    gross_value_estimate: Decimal | None
    iof_estimate: Decimal | None
    ir_estimate: Decimal | None
    net_income_estimate: Decimal | None
    net_value_estimate: Decimal | None
    rates_error: str | None = None
    rates_references: list[RatesReference] = []
    lots: list[LotReturns]
    warnings: list[str]
