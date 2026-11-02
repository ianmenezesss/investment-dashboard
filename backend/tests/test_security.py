from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import Principal, authenticate, verify_jwt
from app.database import Base, Settings, ensure_production_role, get_db, settings
from app.main import app, classify_database_error
from app.models import Operation

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")


def test_production_rejects_local_token_and_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origin="*")


@pytest.mark.parametrize("query", ["", "?sslmode=require", "?sslmode=verify-ca", "?sslmode=disable"])
def test_production_requires_explicit_verify_full_even_with_ca(monkeypatch, query):
    monkeypatch.setenv("PGSSLROOTCERT", "/etc/secrets/supabase-ca.crt")
    with pytest.raises(ValidationError, match="TLS"):
        Settings(
            _env_file=None, environment="production", auth_mode="supabase",
            database_url="postgresql+psycopg://runtime:example@pooler.example:5432/postgres" + query,
            cors_origin="https://portfolio.example", supabase_url="https://auth.example",
            allowed_user_ids=[A],
        )


@pytest.mark.parametrize("query", [
    "?sslmode=verify-full",
    "?sslmode=verify-full&sslrootcert=/etc/secrets/supabase-ca.crt",
])
def test_production_accepts_verified_tls_configuration_without_connecting(query):
    config = Settings(
        _env_file=None, environment="production", auth_mode="supabase",
        database_url="postgresql+psycopg://runtime:example@pooler.example:5432/postgres" + query,
        cors_origin="https://portfolio.example", supabase_url="https://auth.example",
        allowed_user_ids=[A], invitation_admin_ids=[A], supabase_service_role_key="test-only-admin-secret",
        app_public_url="https://portfolio.example",
    )
    assert config.environment == "production"


@pytest.mark.parametrize("unsafe,rls", [(True, True), (False, False)])
def test_production_denies_privileged_role_or_missing_rls(monkeypatch, unsafe, rls):
    monkeypatch.setattr(settings, "environment", "production")
    db = SimpleNamespace(execute=lambda _: SimpleNamespace(one=lambda: SimpleNamespace(unsafe=unsafe, rls=rls)))
    with pytest.raises(HTTPException) as error:
        ensure_production_role(db)
    assert error.value.status_code == 503


@pytest.mark.parametrize("method,path", [("get", "/api/dashboard"), ("get", "/api/operations"), ("get", "/api/export"), ("post", "/api/operations"), ("delete", "/api/operations/1")])
def test_every_financial_endpoint_requires_authentication(method, path):
    # Autenticação deve ocorrer antes de qualquer acesso ao banco.
    def forbidden_db():
        raise AssertionError("Banco acessado sem autenticação")
    app.dependency_overrides[get_db] = forbidden_db
    try:
        client = TestClient(app)
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_jwt_signature_issuer_audience_expiry_and_invited_member_authorization(monkeypatch):
    from app import auth
    private = ec.generate_private_key(ec.SECP256R1())
    other = ec.generate_private_key(ec.SECP256R1())
    config = SimpleNamespace(supabase_url="https://auth.example", allowed_user_ids=[A])
    monkeypatch.setattr(auth, "settings", config)
    now = datetime.now(timezone.utc)
    claims = {"sub": str(A), "iss": "https://auth.example/auth/v1", "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + timedelta(minutes=5)}
    token = lambda data, key=private: jwt.encode(data, key, algorithm="ES256")
    assert verify_jwt(token(claims), private.public_key()) == Principal(A)
    for changed in [dict(claims, exp=now - timedelta(seconds=1)), dict(claims, aud="wrong"), dict(claims, iss="https://wrong.example"), dict(claims, sub="not-a-uuid")]:
        with pytest.raises(HTTPException) as error:
            verify_jwt(token(changed), private.public_key())
        assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        verify_jwt(token(claims, other), private.public_key())
    assert error.value.status_code == 401
    assert verify_jwt(token(dict(claims, sub=str(B))), private.public_key()).user_id == B
    monkeypatch.setattr(auth, "account_access_state", lambda user_id: "active" if user_id == A else None)
    assert auth.require_active_account(Principal(A)).user_id == A
    with pytest.raises(HTTPException) as error:
        auth.require_active_account(Principal(B))
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        verify_jwt(token(dict(claims, role="service_role")), private.public_key())


def test_users_only_read_their_own_portfolio_and_export():
    from datetime import date
    from decimal import Decimal
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i, owner in enumerate([None, A, B]):
            db.add(Operation(owner_id=owner, ticker=f"TEST{i}", kind="BUY", date=date(2026, 1, 1), quantity=Decimal(1), price=Decimal(10), fees=Decimal(0)))
        from app.accounts import AccountMember
        from datetime import datetime, timezone
        db.add_all([
            AccountMember(user_id=A, email="a@example.test", status="active", created_at=datetime.now(timezone.utc)),
            AccountMember(user_id=B, email="b@example.test", status="active", created_at=datetime.now(timezone.utc)),
        ])
        db.commit()

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        client = TestClient(app)
        for owner, ticker in [(None, "TEST0"), (A, "TEST1"), (B, "TEST2")]:
            app.dependency_overrides[authenticate] = lambda owner=owner: Principal(owner)
            assert [op["ticker"] for op in client.get("/api/operations").json()] == [ticker]
            exported = client.get("/api/export").json()
            assert [op["ticker"] for op in exported["operations"]] == [ticker]
            if owner is not None:
                assert exported["account"]["user_id"] == str(owner)
                assert exported["account"]["email"] == ("a@example.test" if owner == A else "b@example.test")
            else:
                assert exported["account"] is None
            assert [op["ticker"] for op in client.get("/api/dashboard").json()["holdings"]] == [ticker]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_private_export_covers_financial_tables_with_owner_scope():
    from datetime import date
    from decimal import Decimal
    from uuid import uuid4
    from app.accounts import AccountMember
    from app.fixed_income.models import ApplicationRevision, Investment, InvestmentArchive, Lot, Movement
    from app.fixed_income.observations import PositionObservation
    from app.financial_events import FinancialEvent, FinancialEventRevision
    from app.wealth_observations import PortfolioValuationObservation

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add_all([
            AccountMember(user_id=A, email="a@example.test", status="active", created_at=now),
            AccountMember(user_id=B, email="b@example.test", status="active", created_at=now),
        ])
        investment_a = Investment(owner_id=A, issuer="Banco fixture A", product_name="CDB fixture A",
            product_type="CDB", remuneration="FIXED", indexer="NONE", contracted_rate=Decimal("12"),
            application_date=date(2025, 1, 1), maturity_date=date(2027, 1, 1))
        investment_b = Investment(owner_id=B, issuer="Banco fixture B", product_name="CDB fixture B",
            product_type="CDB", remuneration="FIXED", indexer="NONE", contracted_rate=Decimal("12"),
            application_date=date(2025, 1, 1), maturity_date=date(2027, 1, 1))
        db.add_all([investment_a, investment_b])
        db.flush()
        lot = Lot(investment_id=investment_a.id, owner_id=A, application_date=date(2025, 1, 1))
        db.add(lot); db.flush()
        movement = Movement(investment_id=investment_a.id, lot_id=lot.id, owner_id=A, kind="APPLICATION",
            date=date(2025, 1, 1), principal_amount=Decimal("100"))
        db.add(movement); db.flush()
        db.add_all([
            PositionObservation(investment_id=investment_a.id, owner_id=A, kind="OPENING", reason="POSITION",
                as_of=date(2025, 1, 1), gross_value=Decimal("100"), net_value=Decimal("100"), source="Fixture"),
            InvestmentArchive(investment_id=investment_a.id, owner_id=A),
            ApplicationRevision(application_id=movement.id, owner_id=A, revision=1, kind="VOID",
                reason="Fixture revision", request_id=uuid4()),
        ])
        event_a = FinancialEvent(owner_id=A, request_id=uuid4(), kind="CONTRIBUTION", event_date=date(2025, 1, 2),
            cash_amount=Decimal("50"), source="Fixture")
        event_b = FinancialEvent(owner_id=B, request_id=uuid4(), kind="CONTRIBUTION", event_date=date(2025, 1, 2),
            cash_amount=Decimal("99"), source="Other fixture")
        db.add_all([event_a, event_b]); db.flush()
        db.add_all([
            FinancialEventRevision(event_id=event_a.id, owner_id=A, revision=1, kind="VOID",
                reason="Fixture correction", request_id=uuid4()),
            PortfolioValuationObservation(owner_id=A, request_id=uuid4(), as_of=date(2025, 1, 3),
                equities_market_value=Decimal("150"), equities_source="Fixture statement",
                fixed_income_coverage="empty", fixed_income_sources=[], missing_fixed_income=[]),
            Operation(owner_id=A, ticker="TEST4", kind="BUY", date=date(2025, 1, 1), quantity=Decimal(1), price=Decimal(10), fees=Decimal(0)),
            Operation(owner_id=B, ticker="OTHR4", kind="BUY", date=date(2025, 1, 1), quantity=Decimal(1), price=Decimal(20), fees=Decimal(0)),
        ])
        db.commit()

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    try:
        exported = TestClient(app).get("/api/export").json()
        assert exported["schema_version"] == 3
        assert exported["account"]["user_id"] == str(A)
        assert [row["ticker"] for row in exported["operations"]] == ["TEST4"]
        expected = {
            "fixed_income_investments", "fixed_income_lots", "fixed_income_movements",
            "fixed_income_observations", "fixed_income_archives", "fixed_income_revisions",
            "financial_events", "financial_event_revisions", "wealth_observations",
        }
        assert expected.issubset(exported)
        assert all(len(exported[key]) == 1 for key in expected)
        assert exported["fixed_income_investments"][0]["owner_id"] == str(A)
        assert exported["financial_events"][0]["cash_amount"] == "50.00000000"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_database_errors_are_sanitized_and_not_cached(caplog):
    def broken_db():
        raise OperationalError("PRIVATE SQL", {"password": "PRIVATE SECRET"}, Exception("PRIVATE HOST"))
    app.dependency_overrides[get_db] = broken_db
    try:
        result = TestClient(app).get("/api/dashboard/equity-history?period=Tudo",
                                    headers={"Authorization": "Bearer test-only-token-not-for-production"})
        assert result.status_code == 503
        assert "PRIVATE" not in result.text
        assert "SQL" not in result.text
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-request-id"]
        assert "route=/api/dashboard/equity-history" in caplog.text
        assert "period=Tudo" not in caplog.text
        assert "exception_category=OperationalError" in caplog.text
        assert "classification=connection_or_operational" in caplog.text
        assert "PRIVATE" not in caplog.text
    finally:
        app.dependency_overrides.clear()


def test_database_permission_sqlstate_is_classified_without_logging_error_details():
    error = ProgrammingError("PRIVATE SQL", {"account": "PRIVATE VALUE"}, SimpleNamespace(sqlstate="42501"))
    assert classify_database_error(error) == "permission"
