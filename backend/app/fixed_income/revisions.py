"""Internal transaction primitive only. No route, feature flag or automatic write grant.

Caller owns commit/rollback. PostgreSQL triggers are the final validation authority.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from .models import ApplicationRevision, Movement


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: str
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    request_id: UUID
    replacement_date: date | None = None
    replacement_amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=8, allow_inf_nan=False)

    @model_validator(mode="after")
    def payload(self):
        if self.kind not in ("REPLACE", "VOID"):
            raise ValueError("Invalid revision kind")
        if self.kind == "REPLACE" and (self.replacement_date is None or self.replacement_amount is None):
            raise ValueError("REPLACE requires a full date and amount")
        if self.kind == "VOID" and (self.replacement_date is not None or self.replacement_amount is not None):
            raise ValueError("VOID cannot replace fields")
        return self


def append_revision(db, application_id: int, data: RevisionInput):
    if db.bind.dialect.name != "postgresql":
        raise RuntimeError("Revision writes require PostgreSQL validation")
    owner = db.info.get("owner_id")
    original = db.scalar(select(Movement).where(Movement.id == application_id, Movement.owner_id == owner, Movement.kind == "APPLICATION"))
    if original is None:
        raise LookupError("Application not found")
    db.execute(text("SET LOCAL lock_timeout='5s'"))
    db.execute(text("SELECT pg_advisory_xact_lock(20001,:id)"), {"id": original.investment_id})
    # Serialize request identities too, including collisions across different contracts.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"fi-revision:{owner}:{data.request_id}"})
    existing = db.scalar(select(ApplicationRevision).where(ApplicationRevision.owner_id == owner, ApplicationRevision.request_id == data.request_id))
    values = dict(application_id=application_id, owner_id=owner, revision=data.expected_revision + 1,
                  **data.model_dump(exclude={"expected_revision"}))
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise ValueError("Idempotency key already used with different content")
        return existing
    row = ApplicationRevision(**values)
    db.add(row)
    db.flush()
    return row
