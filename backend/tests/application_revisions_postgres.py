"""Run only via test_postgres in an empty, disposable PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.auth import Principal, authenticate
from app.main import app
from app.fixed_income.revisions import RevisionInput, append_revision
from app.fixed_income.projection import SQLITE_PROJECTION
from test_fixed_income import A, B, CONTRACT, PATH


def verify_revisions_postgres(engine, client):
    with engine.begin() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "006"
        assert c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='fixed_income_application_revisions'::regclass")).one() == (True, True)
        for role in ("anon", "authenticated", "service_role", "public"):
            leaked=c.scalar(text("""SELECT count(*) FROM pg_class c,
              LATERAL aclexplode(coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) acl
              WHERE c.oid IN ('public.fixed_income_application_revisions'::regclass,'public.fixed_income_application_revisions_id_seq'::regclass)
              AND acl.grantee=CASE WHEN :role='public' THEN 0 ELSE (SELECT oid FROM pg_roles WHERE rolname=:role) END"""), {"role":role})
            assert leaked==0
        # Deliberately opt in ONLY this disposable runtime role; production writes remain ungranted.
        c.execute(text("GRANT SELECT,INSERT ON fixed_income_application_revisions TO investment_test_runtime"))
        c.execute(text("GRANT USAGE ON SEQUENCE fixed_income_application_revisions_id_seq TO investment_test_runtime"))
        c.execute(text("SET LOCAL ROLE investment_test_runtime"))
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            assert not c.scalar(text("SELECT has_table_privilege(current_user,'fixed_income_application_revisions',:p)"), {"p": privilege})

    @contextmanager
    def runtime(owner=A):
        with Session(engine) as db:
            db.execute(text("SET LOCAL ROLE investment_test_runtime"))
            db.execute(text("SELECT set_config('app.user_id',:owner,true),set_config('app.auth_mode','supabase',true)"), {"owner": str(owner) if owner else ""})
            db.info["owner_id"] = owner
            yield db
            db.commit()

    def revise(application, kind="REPLACE", amount="100", revision=0, key=None, day="2025-01-01", owner=A):
        payload = dict(kind=kind, expected_revision=revision, reason="Correção fictícia", request_id=key or uuid4())
        if kind == "REPLACE":
            payload.update(replacement_date=day, replacement_amount=amount)
        with runtime(owner) as db:
            row = append_revision(db, application, RevisionInput(**payload))
            return row.id

    app.dependency_overrides[authenticate] = lambda: Principal(A)
    def create(amount="1000"):
        response = client.post(PATH, json=CONTRACT)
        assert response.status_code == 201, response.text
        investment = response.json()["id"]
        response = client.post(f"{PATH}/{investment}/applications", json={"date":"2025-01-01", "principal_amount":amount})
        assert response.status_code == 201, response.text
        return investment, response.json()

    investment, original = create()
    with engine.connect() as c:
        before = c.execute(text("SELECT * FROM fixed_income_movements WHERE id=:id"), {"id": original["id"]}).one()
        assert c.execute(text("SELECT * FROM fi_effective_movements() ORDER BY id")).all() == c.execute(text(SQLITE_PROJECTION + " ORDER BY m.id")).all()
    key = uuid4()
    event = revise(original["id"], key=key)
    assert revise(original["id"], key=key) == event
    with pytest.raises(ValueError, match="Idempotency"):
        revise(original["id"], amount="200", key=key)
    with pytest.raises(LookupError):
        revise(original["id"], owner=B)
    assert Decimal(client.get(f"{PATH}/{investment}").json()["principal_balance"]) == Decimal("100")
    assert Decimal(client.get(f"{PATH}/{investment}/effective-movements").json()[0]["principal_amount"]) == Decimal("100")
    assert Decimal(client.get(f"{PATH}/{investment}/movements").json()[0]["principal_amount"]) == Decimal("1000")
    # The PostgreSQL redemption trigger must use the corrected, not original, principal.
    assert client.post(f"{PATH}/{investment}/redemptions", json={"lot_id":original["lot_id"], "date":"2025-01-02", "principal_amount":"101"}).status_code == 422
    assert client.post(f"{PATH}/{investment}/redemptions", json={"lot_id":original["lot_id"], "date":"2025-01-02", "principal_amount":"60"}).status_code == 201
    for kwargs in ({"amount":"50", "revision":1}, {"kind":"VOID", "revision":1}, {"day":"2025-01-03", "revision":1}):
        with pytest.raises(DBAPIError):
            revise(original["id"], **kwargs)
    # Direct SQL cannot bypass the effective balance validator.
    with pytest.raises(DBAPIError):
        with runtime() as db:
            db.execute(text("INSERT INTO fixed_income_movements(investment_id,lot_id,owner_id,kind,date,principal_amount,created_at) VALUES (:investment,:lot,:owner,'REDEMPTION','2025-01-03',41,now())"), {"investment": investment, "lot": original["lot_id"], "owner":str(A)})
    with engine.connect() as c:
        assert c.execute(text("SELECT * FROM fixed_income_movements WHERE id=:id"), {"id":original["id"]}).one() == before
        assert c.scalar(text("SELECT count(*) FROM fixed_income_application_revisions WHERE application_id=:id"), {"id":original["id"]}) == 1

    # VOID is terminal, removes the effective lot, and does not make the contract physically empty.
    void_investment, void_original = create()
    revise(void_original["id"], kind="VOID")
    assert client.get(f"{PATH}/{void_investment}").json()["lots"] == []
    assert client.delete(f"{PATH}/{void_investment}/archive").status_code == 409
    with pytest.raises(DBAPIError):
        revise(void_original["id"], revision=1)
    # First effective application must still anchor the original contract date.
    first_investment, first = create()
    assert client.post(f"{PATH}/{first_investment}/applications", json={"date":"2025-01-02", "principal_amount":"20"}).status_code == 201
    with pytest.raises(DBAPIError):
        revise(first["id"], kind="VOID")
    with pytest.raises(DBAPIError):
        revise(first["id"], day="2025-01-02")

    for owner in (B, None):
        with runtime(owner) as db:
            assert db.scalar(text("SELECT count(*) FROM fixed_income_application_revisions")) == 0
            assert db.scalar(text("SELECT count(*) FROM fi_effective_movements() WHERE investment_id=:id"), {"id":investment}) == 0
    for statement in ("UPDATE fixed_income_application_revisions SET reason=reason", "DELETE FROM fixed_income_application_revisions", "TRUNCATE fixed_income_application_revisions"):
        with pytest.raises(DBAPIError):
            with engine.begin() as c:
                c.execute(text(statement))

    # Race two distinct revision requests against the same expected revision.
    race_investment, race_original = create()
    barrier = Barrier(2)
    def race(amount):
        barrier.wait(timeout=10)
        try:
            revise(race_original["id"], amount=amount)
            return "ok"
        except DBAPIError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, ("100", "200")))
    assert sorted(results) == ["conflict", "ok"]
    # Race correction vs redemption: never permit an overdrawn effective balance.
    concurrent_investment, concurrent_original = create()
    barrier = Barrier(2)
    def correction():
        barrier.wait(timeout=10)
        try:
            revise(concurrent_original["id"], amount="50")
            return "ok"
        except DBAPIError:
            return "conflict"
    def redemption():
        barrier.wait(timeout=10)
        return client.post(f"{PATH}/{concurrent_investment}/redemptions", json={"lot_id":concurrent_original["lot_id"], "date":"2025-01-02", "principal_amount":"60"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(correction); b=pool.submit(redemption)
        outcomes=(a.result(timeout=20),b.result(timeout=20))
    assert outcomes in (("ok",422),("conflict",201)), outcomes
    with runtime() as db:
        assert db.scalar(text("SELECT sum(CASE WHEN kind='APPLICATION' THEN principal_amount ELSE -principal_amount END) FROM fi_effective_movements() WHERE investment_id=:id"), {"id":concurrent_investment}) >= 0


    # Same idempotency key concurrently returns one immutable event.
    idem_investment, idem_original = create()
    barrier = Barrier(2); shared_key=uuid4()
    def same_request(_):
        barrier.wait(timeout=10)
        return revise(idem_original["id"], key=shared_key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(same_request, (0,1)))
    assert ids[0]==ids[1]

    # Explicit rollback leaves no event or financial change.
    rollback_investment, rollback_original = create()
    with pytest.raises(RuntimeError, match="abort"):
        with runtime() as db:
            append_revision(db, rollback_original["id"], RevisionInput(kind="VOID", expected_revision=0, reason="Fictício", request_id=uuid4()))
            raise RuntimeError("abort")
    assert Decimal(client.get(f"{PATH}/{rollback_investment}").json()["principal_balance"]) == Decimal("1000")

    # SQL cross-owner forgery, incorrect root kind, null replacement, and stale isolation fail.
    for owner, application, kind, amount in ((B,original["id"],"VOID",None),(A,original["id"],"REPLACE",None)):
        with pytest.raises(DBAPIError):
            with runtime(owner) as db:
                db.execute(text("INSERT INTO fixed_income_application_revisions(application_id,owner_id,revision,kind,replacement_date,replacement_amount,reason,request_id) VALUES (:id,:owner,2,:kind,'2025-01-01',:amount,'Fictício',:key)"), {"id":application,"owner":str(owner),"kind":kind,"amount":amount,"key":str(uuid4())})
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            c.execute(text("INSERT INTO fixed_income_application_revisions(application_id,owner_id,revision,kind,reason,request_id) VALUES (:id,:owner,1,'VOID','Fictício',:key)"), {"id":rollback_original["id"],"owner":str(A),"key":str(uuid4())})

    # Consolidated opening and observations remain immutable boundaries.
    from test_opening_balances import POSITION, contract
    opened=contract(client)
    assert client.post(f"{PATH}/{opened}/opening-balance", json=POSITION).status_code==201
    from datetime import timedelta
    opening_day=date.fromisoformat(POSITION["as_of"])
    application_day=opening_day+timedelta(days=1)
    added=client.post(f"{PATH}/{opened}/applications",json={"date":application_day.isoformat(),"principal_amount":"100"})
    assert added.status_code==201, added.text
    with pytest.raises(DBAPIError):
        revise(added.json()["id"], day=opening_day.isoformat())
