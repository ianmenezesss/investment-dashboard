from datetime import date, datetime, timezone
import json
from pathlib import Path
from uuid import UUID
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.accounts import AccountFixtureLoad, AccountMember
from app.fixed_income.models import Investment, Lot, Movement
from app.fixed_income.observations import PositionObservation
from app.financial_events import FinancialEvent
from app.models import Operation
from app.wealth_observations import PortfolioValuationObservation
from scripts import load_demo_fixture as loader
from scripts.load_demo_fixture import FixtureError, load_fictional_fixture, validate_fixture
from app.database import Base


ADMIN = UUID("11111111-1111-4111-8111-111111111111")
TARGET = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 11, 1)
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "v2-demo-scenario.json"


def fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def setup_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed_member(db, user_id=TARGET):
    db.add(AccountMember(user_id=user_id, email="demo@example.test", status="active",
                         created_at=datetime.now(timezone.utc)))
    db.commit()


def load(db, payload=None, *, admin=ADMIN, target=TARGET, project_verified=True):
    return load_fictional_fixture(db, user_id=target, admin_id=admin, payload=payload or fixture(),
        project_verified=project_verified, today=TODAY)


def test_loader_populates_empty_account_with_fictional_history_and_idempotency_marker(monkeypatch):
    monkeypatch.setattr(loader, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
    engine = setup_db()
    with Session(engine) as db:
        seed_member(db)
        result = load(db)
        assert result == {"status": "loaded", "operations": 3, "events": 4,
                          "wealth_observations": 5, "cdb_contracts": 1}
        assert db.scalar(select(func.count()).select_from(Operation)) == 3
        assert db.scalar(select(func.count()).select_from(Investment)) == 1
        assert db.scalar(select(func.count()).select_from(Lot)) == 1
        assert db.scalar(select(func.count()).select_from(Movement)) == 1
        assert db.scalar(select(func.count()).select_from(PositionObservation)) == 5
        assert {row.as_of.isoformat() for row in db.scalars(select(PositionObservation))} == {
            "2026-06-01", "2026-06-30", "2026-08-31", "2026-09-30", "2026-10-31",
        }
        assert db.scalar(select(func.count()).select_from(FinancialEvent)) == 4
        assert db.scalar(select(func.count()).select_from(PortfolioValuationObservation)) == 5
        marker = db.get(AccountFixtureLoad, TARGET)
        assert marker.fixture_id == "v2-demo-scenario" and marker.loaded_by == ADMIN
        assert all("FICTÍCIO" in row.source for row in db.scalars(select(FinancialEvent)))
        with pytest.raises(FixtureError, match="já foi carregada"):
            load(db)
        assert db.scalar(select(func.count()).select_from(Operation)) == 3
    engine.dispose()


def test_loader_refuses_nonempty_wallet_without_overwriting_anything(monkeypatch):
    monkeypatch.setattr(loader, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
    engine = setup_db()
    with Session(engine) as db:
        seed_member(db)
        db.add(Operation(owner_id=TARGET, ticker="VALE3", kind="BUY", date=date(2026, 1, 1),
                         quantity=1, price=10, fees=0))
        db.commit()
        with pytest.raises(FixtureError, match="não está vazia"):
            load(db)
        assert db.scalar(select(func.count()).select_from(Operation)) == 1
        assert db.scalar(select(func.count()).select_from(AccountFixtureLoad)) == 0
    engine.dispose()


@pytest.mark.parametrize("kwargs, message", [
    ({"admin": TARGET}, "Administrador não autorizado"),
    ({"project_verified": False}, "não foram confirmados"),
])
def test_loader_requires_allowlisted_admin_and_verified_project(kwargs, message, monkeypatch):
    monkeypatch.setattr(loader, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
    engine = setup_db()
    with Session(engine) as db:
        seed_member(db)
        with pytest.raises(FixtureError, match=message):
            load(db, **kwargs)
        assert db.scalar(select(func.count()).select_from(Operation)) == 0
    engine.dispose()


def test_fixture_validation_rejects_future_or_inconsistent_financial_data():
    payload = fixture()
    payload["operations"][0]["date"] = "2026-11-02"
    with pytest.raises(FixtureError, match="futura"):
        validate_fixture(payload, today=TODAY)
    payload = fixture()
    payload["financial_events"][-1]["cash_amount"] = "5.01"
    with pytest.raises(FixtureError, match="inconsistentes"):
        validate_fixture(payload, today=TODAY)
    payload = fixture()
    payload["wealth_observations"].pop()
    with pytest.raises(FixtureError, match="Quantidade"):
        validate_fixture(payload, today=TODAY)
    payload = fixture()
    payload["operations"][1]["date"] = "2026-04-10"
    with pytest.raises(FixtureError, match="ordem cronológica"):
        validate_fixture(payload, today=TODAY)
    payload = fixture()
    payload["wealth_observations"][0]["equities_market_value"] = "0.001"
    with pytest.raises(FixtureError, match="Precisão superior"):
        validate_fixture(payload, today=TODAY)


def test_failure_after_partial_flush_rolls_back_the_entire_fixture(monkeypatch):
    monkeypatch.setattr(loader, "settings", SimpleNamespace(invitation_admin_ids=[ADMIN]))
    engine = setup_db()
    with Session(engine) as db:
        seed_member(db)
        original_flush = db.flush
        calls = 0

        def fail_after_opening(*args, **kwargs):
            nonlocal calls
            calls += 1
            original_flush(*args, **kwargs)
            if calls == 2:
                raise RuntimeError("forced disposable transaction failure")

        monkeypatch.setattr(db, "flush", fail_after_opening)
        with pytest.raises(RuntimeError, match="forced disposable"):
            load(db)
        monkeypatch.undo()
        assert db.scalar(select(func.count()).select_from(Operation)) == 0
        assert db.scalar(select(func.count()).select_from(Investment)) == 0
        assert db.scalar(select(func.count()).select_from(AccountFixtureLoad)) == 0
        assert db.get(AccountMember, TARGET).status == "active"
    engine.dispose()
