"""Pure, deterministic estimates. No IO, ledger mutation or inferred settlement cash."""
from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from .ledger import principal_balances
from .returns_calendar import business_dates
from .returns_schemas import ReturnsSnapshot, LotReturns, InvestmentReturns

IOF_PERCENT = (96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50,
               46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3, 0)
ZERO = Decimal(0)


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def ir_percent(days):
    if days < 0:
        raise ValueError("Invalid tax age")
    return Decimal("22.5" if days <= 180 else "20" if days <= 360 else "17.5" if days <= 720 else "15")


def iof_percent(days):
    if days < 1:
        raise ValueError("IOF day-zero settlement is not modeled")
    return Decimal(IOF_PERCENT[days - 1]) if days < 30 else ZERO


def estimated_taxes(gross_income: Decimal, days: int):
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 64, ROUND_HALF_EVEN
        positive = max(gross_income, ZERO)
        iof = positive * iof_percent(days) / 100 if positive else ZERO
        ir = (positive - iof) * ir_percent(days) / 100
        return money(iof), money(ir)


def estimate_returns(snapshot: ReturnsSnapshot, observations, *, as_of: date, convention=None,
                     calendar=None, tax_profile=None, rates_error=None, references=()):
    contract = snapshot.contract
    if as_of < contract.application_date:
        raise ValueError("Date precedes contract")
    movements = [m for m in snapshot.movements if m.date <= as_of]
    balances = principal_balances(movements)
    results = []
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 64, ROUND_HALF_EVEN
        for lot in snapshot.lots:
            if lot.application_date > as_of:
                continue
            end = min(as_of, contract.maturity_date)
            redeemed = any(m.lot_id == lot.id and m.kind == "REDEMPTION" for m in movements)
            result = LotReturns(lot_id=lot.id, application_date=lot.application_date,
                accrual_end_exclusive=end, tax_basis_date=end, calendar_days=(end - lot.application_date).days,
                principal_balance=balances.get(lot.id, ZERO), status="estimated",
                realized_tax_status="insufficient_information" if redeemed else "not_applicable")
            results.append(result)
            if result.principal_balance == 0:
                result.status = "closed"
                for field in ("gross_income_estimate", "gross_value_estimate", "iof_estimate", "ir_estimate", "net_income_estimate", "net_value_estimate"):
                    setattr(result, field, money(ZERO))
                continue
            if contract.product_type != "CDB" or contract.remuneration != "CDI" or contract.indexer != "CDI":
                result.status = "unsupported_product"
                continue
            if convention != "daily_cdi_pro_rata_decimal_v1":
                result.status = "convention_required"
                continue
            if calendar != "anbima_2024_2026_v1":
                result.status = "calendar_required"
                continue
            expected = business_dates(lot.application_date, end)
            if expected is None:
                result.status = "unsupported_calendar"
                continue
            if rates_error and expected:
                result.status = "rates_unavailable"
                continue
            points, invalid = {}, False
            for point in observations:
                if lot.application_date <= point.date < end:
                    if point.series_code != 12 or point.unit != "% ao dia" or not point.value.is_finite() or point.date not in expected:
                        invalid = True
                    if point.date in points and points[point.date] != point.value:
                        invalid = True
                    points[point.date] = point.value
            result.missing_rate_dates = [day for day in expected if day not in points]
            if invalid:
                result.status = "invalid_rates"
                continue
            if result.missing_rate_dates:
                result.status = "incomplete_history"
                continue
            factor = Decimal(1)
            for day in expected:
                daily = Decimal(1) + points[day] / 100 * contract.contracted_rate / 100
                if daily <= 0:
                    invalid = True
                    break
                factor *= daily
                if factor.adjusted() > 32:
                    invalid = True
                    break
            if invalid:
                result.status = "invalid_rates"
                continue
            result.factor, result.applied_rate_count = factor, len(expected)
            gross = result.principal_balance * (factor - 1)
            result.gross_income_estimate = money(gross)
            result.gross_value_estimate = money(result.principal_balance) + result.gross_income_estimate
            if as_of > contract.maturity_date:
                result.status = "matured_unsettled"
                continue  # no assumed liquidation or actual tax date
            if tax_profile != "br_resident_individual":
                result.status = "tax_profile_required"
                continue
            result.ir_rate_percent = ir_percent(result.calendar_days)
            result.iof_rate_percent = iof_percent(result.calendar_days) if result.calendar_days else None
            result.iof_estimate, result.ir_estimate = estimated_taxes(gross, result.calendar_days)
            result.net_income_estimate = result.gross_income_estimate - result.iof_estimate - result.ir_estimate
            result.net_value_estimate = result.gross_value_estimate - result.iof_estimate - result.ir_estimate
        def total(field):
            values = [getattr(lot, field) for lot in results]
            return sum(values, ZERO) if all(v is not None for v in values) else None
        return InvestmentReturns(investment_id=contract.id, as_of=as_of, ledger_as_of=snapshot.ledger_as_of,
            convention=convention, calendar=calendar, tax_profile=tax_profile,
            principal_balance=sum((lot.principal_balance for lot in results), ZERO),
            status="empty" if not results else "estimated" if all(lot.status in ("estimated", "closed") for lot in results) else "incomplete",
            gross_income_estimate=total("gross_income_estimate"), gross_value_estimate=total("gross_value_estimate"),
            iof_estimate=total("iof_estimate"), ir_estimate=total("ir_estimate"),
            net_income_estimate=total("net_income_estimate"), net_value_estimate=total("net_value_estimate"),
            lots=results, rates_error=rates_error, rates_references=list(references),
            warnings=["estimate_not_settlement", "explicit_contract_convention_required", "proportional_redemption_assumed",
                      "no_coupons_fees_or_spread", "pf_brazil_tax_estimate_only", "realized_taxes_not_inferred_from_cash"])
