from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN
from types import SimpleNamespace
import pytest
from app.finance import summarize
from app.market_data.types import Quote
from app.valuation import value_portfolio

NOW = datetime(2026, 10, 28, 16, tzinfo=timezone.utc)


def operation(kind="BUY", quantity="10", price="20", fees="0", ticker="ITUB4", day=1):
    return SimpleNamespace(id=day, date=date(2026, 1, day), ticker=ticker, kind=kind,
        quantity=D(quantity), price=D(price), fees=D(fees))


def quote(price="24", ticker="ITUB4", **kwargs):
    return Quote(ticker=ticker, price=price, status="ok", quoted_at=NOW, fetched_at=NOW, **kwargs)


def test_partial_sale_fees_and_realized_profit_are_preserved_verbatim():
    ledger = summarize([operation(fees="2"), operation("SELL", "4", "25", "1", day=2)])
    before = deepcopy(ledger)
    result = value_portfolio(ledger, [quote()], now=NOW)
    h = result.holdings[0]
    assert (h.quantity, h.cost, h.average_price) == (D(6), D("121.2"), D("20.2"))
    assert result.realized_profit == D("18.2") == ledger["realized_profit"]
    assert result.market_value == D(144) and result.valuation.unrealized_profit == D("22.8")
    assert h.market_value == D(144) and h.unrealized_profit == D("22.8")
    assert result.valuation.return_percent.quantize(D("0.01")) == D("18.81")
    assert ledger == before and ledger["market_value"] is None
    changed = value_portfolio(ledger, [quote("10")], now=NOW)
    assert changed.realized_profit == result.realized_profit
    assert changed.valuation.unrealized_profit == D("-61.2")


@pytest.mark.parametrize("price,profit,percent", [("30", "100", "50"), ("10", "-100", "-50"), ("20", "0", "0")])
def test_gain_loss_and_flat_position(price, profit, percent):
    result = value_portfolio(summarize([operation()]), [quote(price)], now=NOW)
    assert result.valuation.status == "complete" and result.valuation.is_complete
    assert result.valuation.unrealized_profit == D(profit)
    assert result.valuation.return_percent == D(percent)


def test_multiple_purchases_aggregate_return_is_cost_weighted():
    ledger = summarize([operation(quantity="1", price="10"),
        operation(quantity="1", price="30", day=2), operation(quantity="1", price="100", ticker="PETR4", day=3)])
    result = value_portfolio(ledger, [quote("30"), quote("90", "PETR4")], now=NOW)
    assert result.holdings[0].average_price == D(20)
    assert result.market_value == D(150)
    assert result.valuation.unrealized_profit == D(10)
    assert result.valuation.return_percent.quantize(D("0.01")) == D("7.14")
    assert result.valuation.return_percent != sum(h.return_percent for h in result.holdings) / 2


@pytest.mark.parametrize("quotes", [[], [Quote(ticker="ITUB4", status="disabled", reason="disabled")],
    [Quote(ticker="ITUB4", status="provider_error", reason="network_error")]])
def test_unavailable_never_uses_acquisition_cost_or_zero_as_market_value(quotes):
    result = value_portfolio(summarize([operation()]), quotes, now=NOW)
    assert result.market_value is None
    assert result.valuation.status == "unavailable"
    assert result.valuation.unrealized_profit is None and result.valuation.return_percent is None
    assert result.valuation.missing_tickers == ["ITUB4"]
    assert result.holdings[0].cost == D(200) and result.holdings[0].market_value is None


def test_partial_coverage_exposes_subtotal_not_confirmed_total():
    ledger = summarize([operation(), operation(ticker="PETR4", day=2)])
    result = value_portfolio(ledger, [quote()], now=NOW)
    assert result.market_value is None and not result.valuation.is_complete
    assert result.valuation.status == "partial"
    assert result.valuation.partial_market_value == D(240)
    assert result.valuation.covered_cost == D(200)
    assert result.valuation.covered_positions == 1 and result.valuation.total_positions == 2
    assert result.valuation.unrealized_profit is None and result.valuation.return_percent is None
    assert result.valuation.missing_tickers == ["PETR4"]


def test_stale_coverage_keeps_reference_times_and_estimated_total():
    old = NOW - timedelta(hours=2)
    ledger = summarize([operation(), operation(ticker="PETR4", day=2)])
    cached = Quote(ticker="ITUB4", price="24", status="stale", is_stale=True,
        reason="network_error", quoted_at=old, fetched_at=old, from_cache=True)
    result = value_portfolio(ledger, [cached, quote("24", "PETR4")], now=NOW)
    assert result.market_value == D(480) and result.valuation.status == "stale"
    assert result.valuation.is_complete
    assert result.valuation.quoted_at_min == old and result.valuation.quoted_at_max == NOW
    assert result.holdings[0].quote == cached


@pytest.mark.parametrize("kind", ["expired", "future", "invalid_price", "currency", "duplicate", "invalid_status"])
def test_unusable_or_ambiguous_quotes_do_not_produce_totals(kind):
    q = quote()
    updates = {
        "expired": {"quoted_at": NOW - timedelta(hours=97)},
        "future": {"quoted_at": NOW + timedelta(minutes=2)},
        "invalid_price": {"price": "NaN"}, "currency": {"currency": "USD"},
        "invalid_status": {"status": "provider_error"},
    }
    quotes = [q, q] if kind == "duplicate" else [q.model_copy(update=updates[kind])]
    result = value_portfolio(summarize([operation()]), quotes, now=NOW)
    assert result.market_value is None and result.holdings[0].quote.price is None


def test_empty_and_liquidated_portfolios_keep_realized_results():
    for operations, realized in [([], D(0)), ([operation(), operation("SELL", "10", "30", "2", day=2)], D(98))]:
        result = value_portfolio(summarize(operations), [quote()], now=NOW)
        assert result.market_value == D(0) and result.valuation.unrealized_profit == D(0)
        assert result.valuation.return_percent is None and result.valuation.status == "empty"
        assert result.holdings == [] and result.realized_profit == realized


def test_liquidation_rounding_residue_does_not_create_an_open_position_or_return():
    ledger = summarize([operation(quantity="3", price="0.01", fees="0.01"),
        operation("SELL", "3", "0.02", day=2)])
    result = value_portfolio(ledger, [], now=NOW)
    assert result.valuation.open_cost == 0 and result.market_value == 0
    assert result.valuation.unrealized_profit == 0 and result.valuation.return_percent is None
    assert result.realized_profit == ledger["realized_profit"]


def test_decimal_precision_and_half_even_presentation_without_mutating_context():
    ledger = summarize([operation(quantity="3", price="0.1", fees="0.005")])
    result = value_portfolio(ledger, [quote("0.2")], now=NOW)
    assert result.market_value == D("0.6") and result.valuation.unrealized_profit == D("0.295")
    assert result.valuation.unrealized_profit.quantize(D("0.01"), rounding=ROUND_HALF_EVEN) == D("0.30")
    assert D("0.285").quantize(D("0.01"), rounding=ROUND_HALF_EVEN) == D("0.28")
    assert '"market_value":"0.6"' in result.model_dump_json()
    assert isinstance(result.model_dump(mode="json")["holdings"][0]["average_price"], str)
    large = summarize([operation(quantity="999999999999.99999999")])
    value = value_portfolio(large, [quote("999999999999.99999999")], now=NOW)
    with localcontext() as ctx:
        ctx.prec = 64
        assert value.market_value == D("999999999999.99999999") ** 2


def test_zero_cost_basis_has_no_percentage_and_other_symbols_are_ignored():
    ledger = summarize([operation()])
    ledger["acquisition_cost"] = ledger["holdings"][0]["cost"] = D(0)
    result = value_portfolio(ledger, [quote(), quote("999", "PETR4")], now=NOW)
    assert result.valuation.return_percent is None and result.holdings[0].return_percent is None
    assert result.market_value == D(240) and len(result.holdings) == 1
