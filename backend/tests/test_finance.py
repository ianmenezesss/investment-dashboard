from datetime import date
from decimal import Decimal as D, localcontext
from types import SimpleNamespace
import pytest
from app.finance import summarize


def operation(kind, qty, price, fees="0", day=1):
    return SimpleNamespace(id=day, date=date(2026, 1, day), ticker="ITUB4", kind=kind, quantity=D(qty), price=D(price), fees=D(fees))


def test_weighted_cost_and_partial_sale():
    result = summarize([operation("BUY", "10", "20", "2"), operation("BUY", "10", "30", day=2), operation("SELL", "5", "40", "1", day=3)])
    assert result["acquisition_cost"] == D("376.5")
    assert result["realized_profit"] == D("73.5")
    assert result["holdings"][0]["average_price"] == D("25.1")
    assert result["market_value"] is None


def test_historical_sell_cannot_use_future_purchase():
    with pytest.raises(ValueError):
        summarize([operation("BUY", "10", "20", day=2), operation("SELL", "1", "30")])


def test_empty_and_full_liquidation():
    assert summarize([])["acquisition_cost"] == 0
    result = summarize([operation("BUY", "3", "0.1"), operation("SELL", "3", "0.2", day=2)])
    assert result["realized_profit"] == D("0.3")
    assert result["holdings"] == []


def test_numeric_20_8_purchase_product_keeps_all_decimal_digits():
    maximum = D("999999999999.99999999")
    with localcontext() as context:
        context.prec = 64
        expected = maximum * maximum

    result = summarize([operation("BUY", str(maximum), str(maximum))])

    assert result["total_purchases"] == expected
    assert result["acquisition_cost"] == expected
    assert result["holdings"][0]["cost"] == expected


def test_full_liquidation_removes_exact_cost_after_repeating_average():
    result = summarize([
        operation("BUY", "3", "0.1", "0.01"),
        operation("SELL", "3", "0.2", day=2),
    ])

    assert result["acquisition_cost"] == D("0")
    assert result["realized_profit"] == D("0.29")
    assert result["holdings"] == []
