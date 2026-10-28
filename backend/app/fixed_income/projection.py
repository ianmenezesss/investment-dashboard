"""Effective movements: original identifiers, corrected financial values, no mutations.

PostgreSQL uses the canonical invoker function in migration 006. SQLite's equivalent
SELECT exists for local/offline unit tests; parity is checked in PostgreSQL integration.
"""
from sqlalchemy import text
from .models import Movement

SQLITE_PROJECTION = "SELECT m.id, m.investment_id, m.lot_id, m.owner_id, m.kind,\n CASE WHEN r.kind='REPLACE' THEN r.replacement_date ELSE m.date END AS date,\n CASE WHEN r.kind='REPLACE' THEN r.replacement_amount ELSE m.principal_amount END AS principal_amount,\n m.cash_received, m.created_at\n FROM fixed_income_movements m\n LEFT JOIN fixed_income_application_revisions r ON r.application_id=m.id\n AND r.revision=(SELECT max(r2.revision) FROM fixed_income_application_revisions r2 WHERE r2.application_id=m.id)\n WHERE r.kind IS NULL OR r.kind='REPLACE'"


def effective_movements(db):
    sql = "SELECT * FROM public.fi_effective_movements()" if db.bind.dialect.name == "postgresql" else SQLITE_PROJECTION
    return text(sql).columns(*Movement.__table__.columns).subquery("effective_movements")
