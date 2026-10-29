from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.fixed_income.models import ApplicationRevision, Investment, Lot, Movement
from app.fixed_income.observations import PositionObservation
from app.main import app, quote_service
from app.market_data.types import Quote
from app.models import Operation

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")
PATH = "/api/dashboard/performance"
NOW = datetime.now(timezone.utc)


class QuoteSnapshot:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = []

    async def get_many(self, tickers):
        self.calls.append(list(tickers))
        return self.quotes


def contract(db, owner, name):
    value = Investment(owner_id=owner, issuer="Banco de teste", product_name=name,
        product_type="CDB", remuneration="FIXED", indexer="NONE",
        contracted_rate=Decimal("12"), application_date=date(2025, 1, 1),
        maturity_date=date(2027, 1, 1))
    db.add(value)
    db.flush()
    return value


def movement(db, investment, owner, amount, day, *, kind="APPLICATION", cash_received=None):
    lot = Lot(investment_id=investment.id, owner_id=owner, application_date=date(2025, 1, 1))
    db.add(lot)
    db.flush()
    row = Movement(investment_id=investment.id, lot_id=lot.id, owner_id=owner,
        kind=kind, date=date(2025, 1, day), principal_amount=Decimal(amount),
        cash_received=Decimal(cash_received) if cash_received is not None else None)
    db.add(row)
    db.flush()
    return row


def setup_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def db_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    return engine


def test_performance_combines_effective_ledgers_without_cross_owner_or_manual_double_count():
    engine = setup_client()
    with Session(engine) as db:
        db.add_all([
            Operation(owner_id=A, ticker="ITUB4", kind="BUY", date=date(2025, 1, 1), quantity=Decimal("10"), price=Decimal("20"), fees=Decimal("2")),
            Operation(owner_id=A, ticker="ITUB4", kind="SELL", date=date(2025, 1, 2), quantity=Decimal("4"), price=Decimal("25"), fees=Decimal("1")),
            Operation(owner_id=A, ticker="VALE3", kind="BUY", date=date(2025, 1, 3), quantity=Decimal("2"), price=Decimal("10"), fees=Decimal("0")),
            Operation(owner_id=B, ticker="PETR4", kind="BUY", date=date(2025, 1, 1), quantity=Decimal("9"), price=Decimal("90"), fees=Decimal("0")),
        ])
        ledger = contract(db, A, "CDB com ledger")
        movement(db, ledger, A, "1000", 1)
        movement(db, ledger, A, "400", 5, kind="REDEMPTION", cash_received="430")
        replace_contract = contract(db, A, "CDB substituído")
        replaced = movement(db, replace_contract, A, "50", 2)
        db.add(ApplicationRevision(application_id=replaced.id, owner_id=A, revision=1,
            kind="REPLACE", replacement_date=date(2025, 1, 4), replacement_amount=Decimal("60"),
            reason="Valor corrigido", request_id=uuid4()))
        void_contract = contract(db, A, "CDB anulado")
        voided = movement(db, void_contract, A, "70", 2)
        db.add(ApplicationRevision(application_id=voided.id, owner_id=A, revision=1,
            kind="VOID", reason="Aplicação anulada", request_id=uuid4()))
        manual = contract(db, A, "CDB posição declarada")
        db.add(PositionObservation(investment_id=manual.id, owner_id=A, kind="OBSERVATION",
            reason="POSITION", as_of=date(2025, 1, 6), gross_value=Decimal("300"),
            net_value=Decimal("250"), source="Extrato informado pelo usuário"))
        other = contract(db, B, "CDB de outra carteira")
        movement(db, other, B, "999", 1)
        db.commit()

    quote = Quote(ticker="ITUB4", price="30", status="ok", quoted_at=NOW, fetched_at=NOW)
    quote_snapshot = QuoteSnapshot([quote])  # VALE3 is intentionally uncovered.
    app.dependency_overrides[quote_service] = lambda: quote_snapshot
    try:
        with TestClient(app) as client:
            response = client.get(PATH + "?owner_id=" + str(B))
            assert response.status_code == 200, response.text
            data = response.json()
            assert response.headers["cache-control"] == "no-store"
            assert data["currency"] == "BRL"
            assert Decimal(data["flows"]["equity_purchases_with_fees"]) == Decimal("222")
            assert Decimal(data["flows"]["cdb_applications_principal"]) == Decimal("1060")
            assert Decimal(data["flows"]["equity_sales_after_fees"]) == Decimal("99")
            assert Decimal(data["flows"]["cdb_principal_redemptions"]) == Decimal("400")
            assert Decimal(data["flows"]["net_recorded_flow"]) == Decimal("783")
            assert Decimal(data["equities"]["realized_profit"]) == Decimal("18.2")
            assert Decimal(data["equities"]["acquisition_cost"]) == Decimal("141.2")
            assert data["equities"]["combined_result_before_tax"] is None
            assert data["equities"]["combined_result_status"] == "partial"
            assert Decimal(data["equities"]["partial_unrealized_result_estimate"]) == Decimal("58.8")
            assert data["equities"]["market_value"] is None
            assert data["equities"]["valuation"]["missing_tickers"] == ["VALE3"]
            assert Decimal(data["capital"]["fixed_income_open_principal"]) == Decimal("660")
            assert Decimal(data["capital"]["open_positions_accounted"]) == Decimal("801.2")
            assert Decimal(data["fixed_income"]["effective_open_principal"]) == Decimal("660")
            assert data["fixed_income"]["returns_scope"] == "per_contract_only"
            assert data["fixed_income"]["declared_positions"] == [{
                "asset": "CDB posição declarada", "value": "250.00",
                "basis": "declared_observation", "as_of": "2025-01-06",
            }]
            assert Decimal(data["composition"]["class_totals"]["declared_positions"]) == Decimal("250")
            assert data["portfolio"]["consolidated_market_value_estimate"] is None
            assert data["portfolio"]["return_percent"] is None
            assert quote_snapshot.calls == [["ITUB4", "VALE3"]]

            app.dependency_overrides[authenticate] = lambda: Principal(B)
            other_owner = client.get(PATH).json()
            assert [position["ticker"] for position in other_owner["equities"]["holdings"]] == ["PETR4"]
            assert Decimal(other_owner["flows"]["equity_purchases_with_fees"]) == Decimal("810")
            assert Decimal(other_owner["capital"]["fixed_income_open_principal"]) == Decimal("999")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_performance_empty_wallet_has_zero_ledger_values_and_no_return_claim():
    engine = setup_client()
    quote_snapshot = QuoteSnapshot([])
    app.dependency_overrides[quote_service] = lambda: quote_snapshot
    try:
        with TestClient(app) as client:
            response = client.get(PATH)
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["equities"]["valuation"]["status"] == "empty"
            assert data["equities"]["combined_result_before_tax"] == "0"
            assert data["flows"]["coverage"] == "unavailable"
            assert Decimal(data["flows"]["net_recorded_flow"]) == 0
            assert Decimal(data["capital"]["open_positions_accounted"]) == 0
            assert data["composition"]["declared_positions"] == []
            assert data["portfolio"]["consolidated_market_value_estimate"] is None
            assert data["portfolio"]["return_percent"] is None
            assert quote_snapshot.calls == [[]]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("buy_qty,buy_price,buy_fees,sell_qty,sell_price,sell_fees,quote_price,realized,unrealized,combined", [
    ("10", "20", "2", "4", "25", "1", "24", "18.2", "22.8", "41.0"),
    ("1", "10", "0", "0.5", "8", "0", "6", "-1", "-2", "-3"),
])
def test_combined_result_uses_realized_plus_covered_open_result_only(
        buy_qty, buy_price, buy_fees, sell_qty, sell_price, sell_fees,
        quote_price, realized, unrealized, combined):
    engine = setup_client()
    with Session(engine) as db:
        db.add_all([
            Operation(owner_id=A, ticker="ITUB4", kind="BUY", date=date(2025, 1, 1),
                quantity=Decimal(buy_qty), price=Decimal(buy_price), fees=Decimal(buy_fees)),
            Operation(owner_id=A, ticker="ITUB4", kind="SELL", date=date(2025, 1, 2),
                quantity=Decimal(sell_qty), price=Decimal(sell_price), fees=Decimal(sell_fees)),
        ])
        db.commit()
    quote_snapshot = QuoteSnapshot([Quote(ticker="ITUB4", price=quote_price,
        status="ok", quoted_at=NOW, fetched_at=NOW)])
    app.dependency_overrides[quote_service] = lambda: quote_snapshot
    try:
        with TestClient(app) as client:
            response = client.get(PATH)
            assert response.status_code == 200, response.text
            data = response.json()["equities"]
            assert Decimal(data["realized_profit"]) == Decimal(realized)
            assert Decimal(data["valuation"]["unrealized_profit"]) == Decimal(unrealized)
            assert Decimal(data["combined_result_before_tax"]) == Decimal(combined)
            assert data["combined_result_status"] == "complete"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_performance_requires_authentication_before_database_access():
    def forbidden_db():
        raise AssertionError("Database accessed before authentication")
    app.dependency_overrides[get_db] = forbidden_db
    app.dependency_overrides.pop(authenticate, None)
    try:
        with TestClient(app) as client:
            assert client.get(PATH).status_code == 401
            assert client.get(PATH, headers={"Authorization": "Bearer invalid"}).status_code == 401
    finally:
        app.dependency_overrides.clear()
