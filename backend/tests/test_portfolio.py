from datetime import date
from decimal import Decimal as D
from uuid import uuid4

from app.fixed_income.models import ApplicationRevision
from app.models import Operation
from test_fixed_income import A, B, PATH, apply, client, create, redeem
from app.auth import authenticate, Principal
from app.main import app
from app.database import get_db
from app.portfolio import aggregate_capital_flows, aggregate_composition, _subtract_months


def test_capital_flows_decimal_cutoff_and_separate_gross_withdrawals():
    from types import SimpleNamespace as Row
    operations = [Row(id=1, date=date(2025, 1, 1), kind="BUY", quantity=D("2"), price=D("10.12345678"), fees=D("0.10")),
                  Row(id=2, date=date(2025, 2, 1), kind="SELL", quantity=D("1"), price=D("12"), fees=D("0.25"))]
    movements = [Row(date=date(2025, 3, 1), kind="APPLICATION", principal_amount=D("50.12345678"), id=1),
                 Row(date=date(2025, 3, 5), kind="REDEMPTION", principal_amount=D("20.00000001"), id=2),
                 Row(date=date(2025, 4, 1), kind="REDEMPTION", principal_amount=D("5"), id=3)]
    result = aggregate_capital_flows(operations, movements, start=date(2025, 2, 1), end=date(2025, 3, 15))
    assert [(p["date"], D(p["contributions"]), D(p["redemptions"]), D(p["sales"])) for p in result["points"]] == [
        ("2025-02-01", D(0), D(0), D("11.75")), ("2025-03-01", D("50.12345678"), D(0), D(0)),
        ("2025-03-05", D(0), D("20.00000001"), D(0))]
    assert D(result["net_accumulated"]) == D("38.72037033")
    assert D(result["gross_contributions"]) == D("50.12345678")
    assert D(result["redemptions"]) == D("20.00000001") and D(result["sales"]) == D("11.75")
    assert result["coverage"] == "available" and result["market_value"] is None and result["return"] is None


def test_month_filter_uses_calendar_month_and_clamps_month_end():
    assert _subtract_months(date(2025, 3, 31), 1) == date(2025, 2, 28)


def test_composition_keeps_declared_observations_separate_from_open_lots():
    from types import SimpleNamespace as Row
    investments = [Row(id=1, product_name="CDB com lote"), Row(id=2, product_name="CDB declarado"), Row(id=3, product_name="CDB sem posição")]
    effective = [Row(investment_id=1, lot_id=11, date=date(2025, 1, 1), kind="APPLICATION", principal_amount=D("100"), id=1),
                 Row(investment_id=1, lot_id=11, date=date(2025, 2, 1), kind="REDEMPTION", principal_amount=D("25"), id=2)]
    lots = [Row(investment_id=1, id=11)]
    observations = [Row(investment_id=1, as_of=date(2025, 3, 1), net_value=D("150"), id=1),
                    Row(investment_id=2, as_of=date(2025, 3, 1), net_value=D("80"), id=2)]
    result = aggregate_composition([], effective, investments, lots, observations, as_of=date(2025, 3, 2))
    assert result["fixed_income"] == [{"asset": "CDB com lote", "value": "75", "basis": "effective_open_principal"}]
    assert result["declared_positions"] == [{"asset": "CDB declarado", "value": "80", "as_of": "2025-03-01", "basis": "declared_observation"}]
    assert result["missing_fixed_income"] == ["CDB sem posição"]
    assert result["market_values"] is None and result["coverage"] == "partial"
    assert D(result["class_totals"]["fixed_income_open_principal"]) == D("75")
    assert D(result["class_totals"]["declared_positions"]) == D("80")


def test_private_flow_endpoint_uses_effective_cdb_projection_owner_scope_and_withdrawals(client):
    cdb = create(client)
    application = apply(client, cdb, "100.12345678", "2025-01-01")
    voided = apply(client, cdb, "9.99", "2025-01-02")
    redeem(client, cdb, application["lot_id"], "20.00000001", "2025-03-01")
    session = next(app.dependency_overrides[get_db]())
    session.add(ApplicationRevision(application_id=application["id"], owner_id=A, revision=1, kind="REPLACE",
        replacement_date=date(2025, 2, 1), replacement_amount=D("120.87654321"), reason="Correção de teste", request_id=uuid4()))
    session.add(ApplicationRevision(application_id=voided["id"], owner_id=A, revision=1, kind="VOID",
        reason="Duplicação fictícia", request_id=uuid4()))
    session.add(Operation(owner_id=A, ticker="ABCD3", kind="BUY", date=date(2025, 1, 3), quantity=D("2"), price=D("10.25"), fees=D("0.10")))
    session.add(Operation(owner_id=A, ticker="ABCD3", kind="SELL", date=date(2025, 1, 5), quantity=D("1"), price=D("6.02"), fees=D("0.02")))
    session.add(Operation(owner_id=B, ticker="EFGH3", kind="BUY", date=date(2025, 1, 4), quantity=D("9"), price=D("999"), fees=D("0")))
    session.commit(); session.close()
    response = client.get("/api/dashboard/capital-flows?period=Tudo")
    assert response.status_code == 200, response.text
    data = response.json()
    points = {point["date"]: point for point in data["points"]}
    assert "2025-01-01" not in points and "2025-01-02" not in points and points["2025-02-01"]["contributions"] == "120.87654321"
    assert D(points["2025-03-01"]["redemptions"]) == D("20.00000001")
    assert D(points["2025-01-05"]["sales"]) == D("6")
    assert D(points["2025-01-03"]["contributions"]) == D("20.60")
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    b_data = client.get("/api/dashboard/capital-flows?period=Tudo").json()
    assert D(b_data["gross_contributions"]) == D("8991")
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    assert D(client.get("/api/dashboard/capital-flows?period=Tudo").json()["gross_contributions"]) == D("141.47654321")


def test_composition_endpoint_returns_cost_open_principal_and_unavailable_market_value(client):
    cdb = create(client)
    application = apply(client, cdb, "40", "2025-01-01")
    redeem(client, cdb, application["lot_id"], "10", "2025-02-01")
    session = next(app.dependency_overrides[get_db]())
    session.add(Operation(owner_id=A, ticker="ABCD3", kind="BUY", date=date(2025, 1, 1), quantity=D("3"), price=D("15"), fees=D("1")))
    session.commit(); session.close()
    response = client.get("/api/dashboard/composition")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["equities"][0]["asset"] == "ABCD3" and D(data["equities"][0]["value"]) == D("46")
    assert data["fixed_income"][0]["asset"] == "CDB exemplo" and D(data["fixed_income"][0]["value"]) == D("30")
    assert data["market_values"] is None
