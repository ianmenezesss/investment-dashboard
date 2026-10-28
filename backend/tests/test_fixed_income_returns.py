from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
import pytest
from app.bcb_rates.schemas import Observation
from app.fixed_income.returns_calendar import business_dates
from app.fixed_income.returns_engine import estimate_returns, estimated_taxes, ir_percent, iof_percent
from app.fixed_income.returns_schemas import ReturnsSnapshot, LotSnapshot
from app.fixed_income.schemas import InvestmentOutput, MovementOutput

START = date(2025, 1, 2)
NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
OPTIONS = dict(convention="daily_cdi_pro_rata_decimal_v1", calendar="anbima_2024_2026_v1", tax_profile="br_resident_individual")


def movement(id, kind, principal, day=START, lot=1, cash=None):
    return MovementOutput(id=id, investment_id=1, lot_id=lot, kind=kind, date=day,
        principal_amount=D(principal), cash_received=None if cash is None else D(cash), created_at=NOW)


def snapshot(rate="100", start=START, maturity=date(2026, 12, 31), movements=None, lots=None, **kwargs):
    return ReturnsSnapshot(InvestmentOutput(id=1, issuer="Fictício", product_name="CDB fictício", product_type="CDB",
        remuneration="CDI", indexer="CDI", contracted_rate=D(rate), application_date=start,
        maturity_date=maturity, created_at=NOW, **kwargs), tuple(lots or [LotSnapshot(1, start)]),
        tuple(movements if movements is not None else [movement(1, "APPLICATION", "1000", start)]), NOW)


def rates(start, end, value="0.01"):
    return [Observation(date=day, value=D(value), series_code=12) for day in business_dates(start, end)]


@pytest.mark.parametrize("percentage,factor,gross", [
    ("100", "1.0201", "20.10"), ("110", "1.022121", "22.12"), ("120", "1.024144", "24.14")])
def test_daily_percentage_not_spread_or_annual_rate(percentage, factor, gross):
    result = estimate_returns(snapshot(percentage), rates(START, date(2025, 1, 4), "1"), as_of=date(2025, 1, 4), **OPTIONS)
    lot = result.lots[0]
    assert lot.factor == D(factor) and lot.gross_income_estimate == D(gross)
    assert result.principal_balance == 1000 and lot.applied_rate_count == 2
    if percentage == "100":
        assert lot.iof_estimate == D("18.69") and lot.ir_estimate == D("0.32")
        assert lot.net_income_estimate == D("1.09") and lot.net_value_estimate == D("1001.09")


def test_different_applications_partial_sale_and_no_inferred_realized_taxes():
    ops = [movement(1, "APPLICATION", "1000"), movement(2, "APPLICATION", "200", date(2025, 1, 3), lot=2),
        movement(3, "REDEMPTION", "400", date(2025, 1, 3), cash="450")]
    source = snapshot(movements=ops, lots=[LotSnapshot(1, START), LotSnapshot(2, date(2025, 1, 3))])
    before = deepcopy(source)
    result = estimate_returns(source, rates(START, date(2025, 1, 4), "1"), as_of=date(2025, 1, 4), **OPTIONS)
    assert result.principal_balance == 800
    assert [lot.principal_balance for lot in result.lots] == [D(600), D(200)]
    assert [lot.gross_income_estimate for lot in result.lots] == [D("12.06"), D("2.00")]
    assert result.gross_income_estimate == D("14.06")  # withdrawn capital's income not counted again
    assert result.lots[0].realized_tax_status == "insufficient_information"
    assert result.lots[0].realized_ir is None and result.lots[0].realized_income is None
    assert source == before
    # Cash can be unknown or differ: neither changes remaining principal/estimated return.
    ops[-1] = movement(3, "REDEMPTION", "400", date(2025, 1, 3), cash=None)
    other = estimate_returns(snapshot(movements=ops, lots=source.lots), rates(START, date(2025, 1, 4), "1"), as_of=date(2025, 1, 4), **OPTIONS)
    assert other.gross_income_estimate == result.gross_income_estimate


def test_full_redemption_keeps_zero_open_position_without_claiming_past_income():
    source = snapshot(movements=[movement(1, "APPLICATION", "1000"), movement(2, "REDEMPTION", "1000", date(2025, 1, 3))])
    result = estimate_returns(source, [], as_of=date(2025, 1, 4), **OPTIONS)
    assert result.principal_balance == result.gross_income_estimate == result.net_value_estimate == 0
    assert result.lots[0].status == "closed" and result.lots[0].realized_iof is None


@pytest.mark.parametrize("days,percent", [(180, "22.5"), (181, "20"), (360, "20"), (361, "17.5"), (720, "17.5"), (721, "15")])
def test_ir_boundaries_use_calendar_days_since_each_lot(days, percent):
    start = date(2024, 1, 2)
    end = start + timedelta(days=days)
    result = estimate_returns(snapshot(start=start), rates(start, end), as_of=end, **OPTIONS)
    assert result.lots[0].calendar_days == days and result.lots[0].ir_rate_percent == D(percent)
    assert result.iof_estimate == 0
    assert estimated_taxes(D(100), days) == (D(0), D(percent))


@pytest.mark.parametrize("days,percent", list(enumerate([
    96,93,90,86,83,80,76,73,70,66,63,60,56,53,50,46,43,40,36,33,30,26,23,20,16,13,10,6,3,0], 1)))
def test_iof_each_day_and_ir_base_after_iof(days, percent):
    assert iof_percent(days) == D(percent)
    iof, ir = estimated_taxes(D(100), days)
    assert iof == D(percent)
    assert ir == ((D(100) - D(percent)) * D("0.225")).quantize(D("0.01"))


def test_iof_exemption_day_zero_and_loss():
    assert iof_percent(31) == iof_percent(721) == 0
    assert estimated_taxes(D(-10), 1) == (D(0), D(0))
    with pytest.raises(ValueError): iof_percent(0)
    with pytest.raises(ValueError): ir_percent(-1)
    result = estimate_returns(snapshot(), [], as_of=START, **OPTIONS)
    assert result.gross_income_estimate == result.ir_estimate == result.iof_estimate == 0


def test_missing_rates_never_produce_a_confirmed_total_or_fabricated_holiday_rate():
    end = date(2025, 1, 7)
    for data in ([], rates(START, end)[:-1]):
        result = estimate_returns(snapshot(), data, as_of=end, **OPTIONS)
        assert result.status == "incomplete" and result.gross_value_estimate is None
        assert result.principal_balance == 1000 and result.lots[0].missing_rate_dates
    assert business_dates(date(2025, 1, 1), date(2025, 1, 6)) == (date(2025, 1, 2), date(2025, 1, 3))
    assert business_dates(date(2026, 2, 16), date(2026, 2, 18)) == ()
    assert business_dates(date(2023, 12, 31), START) is None


@pytest.mark.parametrize("options,status", [
    ({"convention": None}, "convention_required"), ({"calendar": None}, "calendar_required"),
    ({"tax_profile": None}, "tax_profile_required")])
def test_conventions_and_tax_profile_are_explicit_not_guessed(options, status):
    result = estimate_returns(snapshot(), rates(START, date(2025, 1, 4)), as_of=date(2025, 1, 4), **(OPTIONS | options))
    assert result.lots[0].status == status and result.net_value_estimate is None


def test_maturity_caps_accrual_but_does_not_infer_actual_settlement_or_tax_date():
    result = estimate_returns(snapshot(maturity=date(2025, 1, 3)), rates(START, date(2025, 1, 4)), as_of=date(2025, 1, 4), **OPTIONS)
    assert result.lots[0].applied_rate_count == 1
    assert result.lots[0].accrual_end_exclusive == date(2025, 1, 3)
    assert result.principal_balance == 1000 and result.net_value_estimate is None
    assert result.lots[0].status == "matured_unsettled"


def test_historical_asof_ignores_later_redemption_and_empty_ledger_is_zero():
    source = snapshot(movements=[movement(1, "APPLICATION", "1000"), movement(2, "REDEMPTION", "1000", date(2025, 2, 1))])
    result = estimate_returns(source, rates(START, date(2025, 1, 4)), as_of=date(2025, 1, 4), **OPTIONS)
    assert result.principal_balance == 1000 and result.lots[0].realized_tax_status == "not_applicable"
    empty = ReturnsSnapshot(source.contract, (), (), NOW)
    result = estimate_returns(empty, [], as_of=START, **OPTIONS)
    assert result.status == "empty" and result.principal_balance == 0
    with pytest.raises(ValueError): estimate_returns(source, [], as_of=date(2024, 1, 1), **OPTIONS)


def test_decimal_precision_rounding_and_no_intermediate_currency_rounding():
    end = date(2025, 2, 5)
    data = rates(START, end, "0.012345678901")
    result = estimate_returns(snapshot("110.12345678"), data, as_of=end, **OPTIONS)
    with localcontext() as ctx:
        ctx.prec = 64
        factor = (D(1) + D("0.012345678901") / 100 * D("110.12345678") / 100) ** len(data)
        assert abs(result.lots[0].factor - factor) < D("1e-60")
    assert result.net_value_estimate == result.gross_value_estimate - result.ir_estimate - result.iof_estimate
    assert estimated_taxes(D("0.10"), 181) == (D("0.00"), D("0.02"))


def test_invalid_or_unsupported_data_does_not_escape_as_value():
    data = rates(START, date(2025, 1, 4))
    for observations in ([data[0].model_copy(update={"series_code": 11}), data[1]],
                         data + [data[0].model_copy(update={"value": D(2)})]):
        result = estimate_returns(snapshot(), observations, as_of=date(2025, 1, 4), **OPTIONS)
        assert result.lots[0].status == "invalid_rates" and result.gross_income_estimate is None
    source = snapshot()
    source.contract.remuneration = "FIXED"
    assert estimate_returns(source, data, as_of=date(2025, 1, 4), **OPTIONS).lots[0].status == "unsupported_product"
    result = estimate_returns(snapshot(start=date(2023, 1, 2)), [], as_of=START, **OPTIONS)
    assert result.lots[0].status == "unsupported_calendar"


def test_partial_coverage_cannot_be_reported_as_total_income():
    source = snapshot(movements=[movement(1, "APPLICATION", "1000"),
        movement(2, "APPLICATION", "200", date(2025, 1, 3), lot=2)],
        lots=[LotSnapshot(1, START), LotSnapshot(2, date(2025, 1, 3))])
    result = estimate_returns(source, rates(START, date(2025, 1, 4))[1:], as_of=date(2025, 1, 4), **OPTIONS)
    assert result.lots[0].gross_income_estimate is None and result.lots[1].gross_income_estimate is not None
    assert result.gross_income_estimate is None and result.net_value_estimate is None
    assert result.principal_balance == 1200


def test_external_decimal_context_does_not_change_engine_output():
    data = rates(START, date(2025, 1, 4), "0.012345678901")
    source = snapshot("110.12345678")
    expected = estimate_returns(source, data, as_of=date(2025, 1, 4), **OPTIONS)
    with localcontext() as ctx:
        ctx.prec = 6
        actual = estimate_returns(source, data, as_of=date(2025, 1, 4), **OPTIONS)
    assert actual == expected
