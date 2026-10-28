from copy import deepcopy
from decimal import Decimal as D, localcontext
import pytest
from app.finance import summarize
from app.price_basis import purchase_price_basis
from app.valuation import value_portfolio
from test_valuation import operation, quote, NOW


def evaluate(ops, quotes=None):
    return value_portfolio(summarize(ops), [quote()] if quotes is None else quotes,
        price_basis=purchase_price_basis(ops), now=NOW)


def test_fees_can_turn_asset_appreciation_into_financial_loss():
    result = evaluate([operation(price="20", fees="20")], [quote("21")])
    h = result.holdings[0]
    assert h.average_trade_price == D(20)
    assert h.average_price == D(22)
    assert h.purchase_cost_without_fees == D(200)
    assert h.price_appreciation_percent == D(5)
    assert h.unrealized_profit == D(-10)
    assert h.return_percent < 0
    assert result.realized_profit == 0


def test_multiple_purchases_partial_sale_and_new_purchase_use_remaining_weighted_basis():
    ops = [operation(quantity="10", price="10", fees="2"),
        operation(quantity="10", price="30", fees="4", day=2),
        operation("SELL", "5", "25", "1", day=3),
        operation(quantity="5", price="40", fees="2", day=4)]
    before = deepcopy(ops)
    result = evaluate(list(reversed(ops)), [quote("30")])
    h = result.holdings[0]
    assert h.quantity == 20 and h.purchase_cost_without_fees == 500
    assert h.average_trade_price == 25 and h.price_appreciation_percent == 20
    assert h.cost == D("506.5") and h.average_price == D("25.325")
    assert h.unrealized_profit == D("93.5")
    assert result.realized_profit == D("22.5")
    assert result.realized_profit == summarize(ops)["realized_profit"]
    assert ops == before


def test_full_exit_resets_reference_before_reentry_and_closed_positions_are_absent():
    ops = [operation(quantity="3", price="1", fees="1"), operation("SELL", "3", "2", day=2)]
    assert evaluate(ops).holdings == []
    ops.append(operation(quantity="2", price="30", fees="2", day=3))
    h = evaluate(ops).holdings[0]
    assert h.average_trade_price == 30 and h.purchase_cost_without_fees == 60
    assert h.average_price == 31 and h.price_appreciation_percent == -20


@pytest.mark.parametrize("quotes", [[], [quote("24", currency="USD")]])
def test_missing_or_invalid_quote_keeps_purchase_reference_but_never_invents_appreciation(quotes):
    h = evaluate([operation(fees="2")], quotes).holdings[0]
    assert h.average_trade_price == 20 and h.average_price == D("20.2")
    assert h.price_appreciation_percent is None and h.unrealized_profit is None


@pytest.mark.parametrize("basis", [None, {}, {"ITUB4": {"quantity": D(9), "cost": D(180)}}])
def test_absent_or_inconsistent_basis_is_not_inferred_from_fee_inclusive_cost(basis):
    h = value_portfolio(summarize([operation(fees="2")]), [quote()], price_basis=basis, now=NOW).holdings[0]
    assert h.average_trade_price is None and h.price_appreciation_percent is None
    assert h.unrealized_profit == D(38)


def test_decimal_precision_and_independent_tickers():
    ops = [operation(quantity="999999999999.12345678", price="123456789.12345678"),
        operation(ticker="PETR4", price="10", fees="3")]
    basis = purchase_price_basis(ops)
    with localcontext() as ctx:
        ctx.prec = 64
        assert basis["ITUB4"]["cost"] == D("999999999999.12345678") * D("123456789.12345678")
    assert basis["PETR4"]["cost"] == 100


def test_zero_basis_has_no_percentage_and_overselling_is_rejected():
    h = evaluate([operation(price="0")]).holdings[0]
    assert h.average_trade_price == 0 and h.price_appreciation_percent is None
    with pytest.raises(ValueError):
        purchase_price_basis([operation("SELL")])


def test_fractional_purchase_sale_and_display_rounding_preserve_decimal_precision():
    ops = [operation(quantity="3", price="0.1", fees="0.03"),
        operation("SELL", "1", "0.2", "0.01", day=2)]
    h = evaluate(ops, [quote("0.15")]).holdings[0]
    assert h.purchase_cost_without_fees == D("0.2")
    assert h.average_trade_price == D("0.1") and h.average_price == D("0.11")
    assert h.price_appreciation_percent == 50
    assert h.unrealized_profit == D("0.08")
    assert h.return_percent.quantize(D("0.01")) == D("36.36")


def test_without_fees_both_indicators_agree():
    h = evaluate([operation()]).holdings[0]
    assert h.average_price == h.average_trade_price
    assert h.return_percent == h.price_appreciation_percent == 20
