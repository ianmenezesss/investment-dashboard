"""Typed read-only snapshot joining existing ledger, composition and valuation rules."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Literal

from pydantic import BaseModel

from .valuation import PortfolioValuation


class RecordedFlows(BaseModel):
    coverage_start: date | None
    coverage_end: date | None
    coverage: Literal["available", "partial", "unavailable"]
    equity_purchases_with_fees: Decimal
    cdb_applications_principal: Decimal
    equity_sales_after_fees: Decimal
    cdb_principal_redemptions: Decimal
    recorded_contributions: Decimal
    recorded_withdrawals: Decimal
    net_recorded_flow: Decimal


class CompositionPosition(BaseModel):
    asset: str
    value: Decimal
    basis: str
    as_of: date | None = None


class CompositionTotals(BaseModel):
    equities_open_cost: Decimal
    fixed_income_open_principal: Decimal
    declared_positions: Decimal


class CompositionSnapshot(BaseModel):
    as_of: date
    equities: list[CompositionPosition]
    fixed_income: list[CompositionPosition]
    declared_positions: list[CompositionPosition]
    missing_fixed_income: list[str]
    market_values: None = None
    coverage: Literal["available", "partial"]
    missing_components: list[str]
    equity_basis: str
    fixed_income_basis: str
    declared_values_separate: bool
    class_totals: CompositionTotals


class AccountedCapital(BaseModel):
    equities_open_cost: Decimal
    fixed_income_open_principal: Decimal
    open_positions_accounted: Decimal
    equity_open_share_percent: Decimal | None
    fixed_income_open_share_percent: Decimal | None
    basis: Literal["equity_open_acquisition_cost_plus_effective_cdb_principal"] = (
        "equity_open_acquisition_cost_plus_effective_cdb_principal"
    )


class EquityPerformance(PortfolioValuation):
    combined_result_before_tax: Decimal | None
    combined_result_status: Literal["complete", "stale", "partial", "unavailable", "empty"]
    partial_unrealized_result_estimate: Decimal
    result_scope: Literal["realized_plus_open_unrealized_before_tax"] = "realized_plus_open_unrealized_before_tax"


class FixedIncomePerformance(BaseModel):
    effective_open_principal: Decimal
    declared_positions: list[CompositionPosition]
    missing_positions: list[str]
    returns_scope: Literal["per_contract_only"] = "per_contract_only"


class PortfolioPerformanceContext(BaseModel):
    consolidated_market_value_estimate: None = None
    return_percent: None = None
    status: Literal["not_comparable", "insufficient_historical_data"] = "not_comparable"


class FinancialPerformance(BaseModel):
    as_of: date
    ledger_as_of: datetime
    currency: Literal["BRL"] = "BRL"
    flows: RecordedFlows
    capital: AccountedCapital
    equities: EquityPerformance
    fixed_income: FixedIncomePerformance
    composition: CompositionSnapshot
    portfolio: PortfolioPerformanceContext = PortfolioPerformanceContext()


def build_financial_performance(*, as_of: date, ledger_as_of: datetime, flows: dict,
                                valuation: PortfolioValuation, composition: dict) -> FinancialPerformance:
    """Join existing calculations; no new source-of-truth or financial inference."""
    composition_snapshot = CompositionSnapshot.model_validate(composition)
    with localcontext() as context:
        context.prec, context.rounding = 64, ROUND_HALF_EVEN
        open_equity_cost = valuation.acquisition_cost
        open_cdb_principal = composition_snapshot.class_totals.fixed_income_open_principal
        accounted_open_positions = open_equity_cost + open_cdb_principal
        equity_share = fixed_income_share = None
        if accounted_open_positions:
            equity_share = (open_equity_cost * 100 / accounted_open_positions).quantize(Decimal("0.1"))
            fixed_income_share = (open_cdb_principal * 100 / accounted_open_positions).quantize(Decimal("0.1"))
        partial_unrealized = (valuation.valuation.partial_market_value
                              - valuation.valuation.covered_cost)
        combined_result = None
        if valuation.valuation.is_complete and valuation.valuation.unrealized_profit is not None:
            combined_result = valuation.realized_profit + valuation.valuation.unrealized_profit

        recorded_flows = RecordedFlows(
            coverage_start=flows["coverage_start"],
            coverage_end=flows["coverage_end"],
            coverage=flows["coverage"],
            equity_purchases_with_fees=Decimal(flows["equity_purchases"]),
            cdb_applications_principal=Decimal(flows["cdb_applications"]),
            equity_sales_after_fees=Decimal(flows["equity_sale_proceeds"]),
            cdb_principal_redemptions=Decimal(flows["cdb_redemptions"]),
            recorded_contributions=Decimal(flows["cumulative_contributions"]),
            recorded_withdrawals=Decimal(flows["cumulative_withdrawals"]),
            net_recorded_flow=Decimal(flows["net_accumulated"]),
        )
        return FinancialPerformance(
            as_of=as_of,
            ledger_as_of=ledger_as_of,
            flows=recorded_flows,
            capital=AccountedCapital(
                equities_open_cost=open_equity_cost,
                fixed_income_open_principal=open_cdb_principal,
                open_positions_accounted=accounted_open_positions,
                equity_open_share_percent=equity_share,
                fixed_income_open_share_percent=fixed_income_share,
            ),
            equities=EquityPerformance(
                **valuation.model_dump(),
                combined_result_before_tax=combined_result,
                combined_result_status=valuation.valuation.status,
                partial_unrealized_result_estimate=partial_unrealized,
            ),
            fixed_income=FixedIncomePerformance(
                effective_open_principal=open_cdb_principal,
                declared_positions=composition_snapshot.declared_positions,
                missing_positions=composition_snapshot.missing_fixed_income,
            ),
            composition=composition_snapshot,
        )
