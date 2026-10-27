"""Mesmos casos fictícios usados pelo cálculo decimal no frontend."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.finance import summarize

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared/finance-cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_demo_and_backend_share_financial_contract(case):
    operations = []
    for raw in case["operations"]:
        values = dict(raw, date=date.fromisoformat(raw["date"]))
        for field in ("quantity", "price", "fees"):
            values[field] = Decimal(raw[field])
        operations.append(SimpleNamespace(**values))
    if case.get("invalid"):
        with pytest.raises(ValueError):
            summarize(operations)
        return
    result = summarize(operations)
    expected = case["expected"]
    for field in ("acquisition_cost", "total_purchases", "sale_proceeds", "realized_profit"):
        assert result[field] == Decimal(expected[field])
    assert len(result["holdings"]) == len(expected["holdings"])
    for actual, target in zip(result["holdings"], expected["holdings"]):
        assert actual["ticker"] == target["ticker"]
        for field in ("quantity", "cost", "average_price"):
            assert actual[field] == Decimal(target[field])
