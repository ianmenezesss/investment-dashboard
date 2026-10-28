from datetime import date
from decimal import Decimal
from uuid import uuid4
import importlib.util
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.fixed_income.models import Investment, Lot, Movement, ApplicationRevision
from app.fixed_income.projection import effective_movements, SQLITE_PROJECTION
from app.fixed_income.revisions import RevisionInput, RevisionBody, append_revision
from app.fixed_income.ledger import principal_balances
from test_fixed_income import A, CONTRACT


def test_projection_frozen_sql_matches_migration():
    path = Path("migrations/versions/006_application_revisions.py")
    spec = importlib.util.spec_from_file_location("revision006", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.PROJECTION_SQL == SQLITE_PROJECTION


@pytest.mark.parametrize("payload", [
    {"kind": "REPLACE"}, {"kind": "VOID", "replacement_amount": "1"},
    {"kind": "OTHER"}, {"kind": "VOID", "reason": "  "},
    {"kind": "REPLACE", "replacement_date": "2025-01-01", "replacement_amount": "NaN"},
])
def test_invalid_revision_payload(payload):
    with pytest.raises(ValidationError):
        RevisionInput(**({"reason": "FictÃ­cio", "request_id": uuid4(), "expected_revision": 0} | payload))


@pytest.mark.parametrize("payload", [
    {"kind":"REPLACE", "expected_revision":0, "reason":"x"},
    {"kind":"VOID", "expected_revision":0, "reason":"x", "replacement_amount":"1"},
    {"kind":"VOID", "expected_revision":0, "reason":"  "},
])
def test_public_revision_body_rejects_incomplete_or_ambiguous_payload(payload):
    with pytest.raises(ValidationError):
        RevisionBody(**payload)


def test_projection_preserves_originals_and_replaces_whole_value_then_voids():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["owner_id"] = A
        investment = Investment(**(CONTRACT | {"application_date": date(2025,1,1), "maturity_date": date(2027,1,1), "contracted_rate": Decimal("12")}), owner_id=A)
        db.add(investment); db.flush()
        lot = Lot(investment_id=investment.id, owner_id=A, application_date=date(2025,1,1))
        db.add(lot); db.flush()
        original = Movement(investment_id=investment.id, lot_id=lot.id, owner_id=A, kind="APPLICATION", date=lot.application_date, principal_amount=Decimal("1000"))
        db.add(original); db.flush()
        def projected():
            return db.execute(select(effective_movements(db))).mappings().all()
        assert projected()[0]["principal_amount"] == Decimal("1000")
        db.add(ApplicationRevision(application_id=original.id, owner_id=A, revision=1, kind="REPLACE", replacement_date=date(2025,1,1), replacement_amount=Decimal("100"), reason="FictÃ­cio", request_id=uuid4()))
        db.flush()
        assert projected()[0]["principal_amount"] == Decimal("100")
        db.add(ApplicationRevision(application_id=original.id, owner_id=A, revision=2, kind="VOID", reason="Duplicado fictÃ­cio", request_id=uuid4()))
        db.flush()
        assert projected() == []
        assert db.get(Movement, original.id).principal_amount == Decimal("1000")
        assert db.get(Lot, lot.id).application_date == date(2025,1,1)
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            append_revision(db, original.id, RevisionInput(kind="VOID", reason="FictÃ­cio", request_id=uuid4(), expected_revision=2))
    engine.dispose()


# SQLite inserts below are fixtures only, never an application write path.
from test_fixed_income import client, create, apply, PATH
from app.main import app
from app.database import get_db


def test_all_financial_readers_use_effective_values_but_audit_keeps_original(client):
    investment = create(client)
    response = apply(client, investment)
    original = response
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    db.add(ApplicationRevision(application_id=original["id"], owner_id=A, revision=1, kind="REPLACE", replacement_date=date(2025,1,1), replacement_amount=Decimal("25"), reason="Fictício", request_id=uuid4()))
    db.commit(); generator.close()
    assert Decimal(client.get(f"{PATH}/{investment}").json()["principal_balance"]) == Decimal("25")
    assert Decimal(client.get(f"{PATH}/{investment}/effective-movements").json()[0]["principal_amount"]) == Decimal("25")
    assert Decimal(client.get(f"{PATH}/{investment}/movements").json()[0]["principal_amount"]) == Decimal(original["principal_amount"])
    returns = client.get(f"{PATH}/{investment}/returns?as_of=2025-01-03").json()
    assert Decimal(returns["principal_balance"]) == Decimal("25")
    assert client.post(f"{PATH}/{investment}/redemptions", json={"lot_id":original["lot_id"], "date":"2025-01-02", "principal_amount":"26"}).status_code == 422
    assert client.post(f"{PATH}/{investment}/applications/{original['id']}/revisions", json={}).status_code == 422


def test_effective_dates_drive_lots_and_returns_and_void_does_not_create_cash(client):
    investment = create(client)
    apply(client, investment, "100", "2025-01-01")
    second = apply(client, investment, "200", "2025-01-02")
    generator = app.dependency_overrides[get_db](); db=next(generator)
    db.add(ApplicationRevision(application_id=second["id"], owner_id=A, revision=1, kind="REPLACE", replacement_date=date(2025,1,3), replacement_amount=Decimal("50"), reason="Fictício", request_id=uuid4()))
    db.commit(); generator.close()
    detail=client.get(f"{PATH}/{investment}").json()
    assert detail["lots"][1]["application_date"] == "2025-01-03"
    before=client.get(f"{PATH}/{investment}/returns?as_of=2025-01-02").json()
    assert Decimal(before["principal_balance"]) == Decimal("100")
    after=client.get(f"{PATH}/{investment}/returns?as_of=2025-01-04").json()
    assert after["lots"][1]["calendar_days"] == 1
    assert Decimal(after["principal_balance"]) == Decimal("150")
    generator=app.dependency_overrides[get_db](); db=next(generator)
    db.add(ApplicationRevision(application_id=second["id"], owner_id=A, revision=2, kind="VOID", reason="Duplicado fictício", request_id=uuid4()))
    db.commit(); generator.close()
    effective=client.get(f"{PATH}/{investment}/effective-movements").json()
    assert len(effective)==1 and effective[0]["cash_received"] is None
    assert len(client.get(f"{PATH}/{investment}/movements").json())==2
    assert len(client.get(f"{PATH}/{investment}").json()["lots"])==1
