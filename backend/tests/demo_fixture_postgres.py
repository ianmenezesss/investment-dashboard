"""Disposable-PostgreSQL coverage for the admin-only fictional fixture loader."""
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Operation
from scripts.load_demo_fixture import FixtureError, load_fictional_fixture


ADMIN = UUID("c8c8c8c8-c8c8-4c8c-8c8c-c8c8c8c8c8c8")
EMPTY = UUID("a6a6a6a6-a6a6-4a6a-8a6a-a6a6a6a6a6a6")
NONEMPTY = UUID("b7b7b7b7-b7b7-4b7b-8b7b-b7b7b7b7b7b7")
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "v2-demo-scenario.json"


def verify_demo_fixture_postgres(engine, runtime_engine):
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO public.account_members(user_id,email,status)
          VALUES (:empty,'empty-demo@example.test','active'),(:nonempty,'nonempty-demo@example.test','active')"""),
          {"empty": EMPTY, "nonempty": NONEMPTY})
        connection.execute(text("""INSERT INTO public.operations(owner_id,ticker,kind,date,quantity,price,fees,created_at)
          VALUES (:owner,'TEST3','BUY','2026-01-01',1,10,0,now())"""), {"owner": NONEMPTY})

    with patch("scripts.load_demo_fixture.settings", SimpleNamespace(invitation_admin_ids=[ADMIN])):
        with Session(runtime_engine) as db:
            result = load_fictional_fixture(db, user_id=EMPTY, admin_id=ADMIN, payload=payload,
                                            project_verified=True, today=date(2026, 11, 1))
            assert result == {"status": "loaded", "operations": 3, "events": 4,
                              "wealth_observations": 5, "cdb_contracts": 1}
        with Session(runtime_engine) as db:
            with pytest.raises(FixtureError, match="não está vazia"):
                load_fictional_fixture(db, user_id=NONEMPTY, admin_id=ADMIN, payload=payload,
                                       project_verified=True, today=date(2026, 11, 1))

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM public.operations WHERE owner_id=:owner"),
                                 {"owner": EMPTY}) == 3
        assert connection.scalar(text("SELECT count(*) FROM public.fixed_income_observations WHERE owner_id=:owner"),
                                 {"owner": EMPTY}) == 5
        assert connection.scalar(text("SELECT count(*) FROM public.portfolio_valuation_observations WHERE owner_id=:owner"),
                                 {"owner": EMPTY}) == 5
        assert connection.scalar(text("SELECT count(*) FROM public.account_fixture_loads WHERE user_id=:owner"),
                                 {"owner": EMPTY}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.operations WHERE owner_id=:owner"),
                                 {"owner": NONEMPTY}) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.account_fixture_loads WHERE user_id=:owner"),
                                 {"owner": NONEMPTY}) == 0
