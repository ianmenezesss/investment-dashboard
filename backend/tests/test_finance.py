from datetime import date
from decimal import Decimal as D
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
