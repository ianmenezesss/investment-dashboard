"""Append-only application revision API and transaction primitive.

PostgreSQL triggers are the final validation authority; API mutations commit only after
the insert and all validation triggers succeed.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Header
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
import json
from .models import ApplicationRevision, Movement
from ..access import private_db
from .router import owned_investment, is_archived
from .projection import effective_movements
from .ledger import principal_balances
from .schemas import MovementOutput


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


class RevisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: str
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    replacement_date: date | None = None
    replacement_amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=8, allow_inf_nan=False)

    @model_validator(mode="after")
    def payload(self):
        RevisionInput(kind=self.kind, expected_revision=self.expected_revision, reason=self.reason,
            request_id=UUID(int=0), replacement_date=self.replacement_date, replacement_amount=self.replacement_amount)
        return self


def append_revision(db, application_id: int, data: RevisionInput, *, investment_id: int | None = None):
    if db.bind.dialect.name != "postgresql":
        raise RuntimeError("Revision writes require PostgreSQL validation")
    owner = db.info.get("owner_id")
    original = db.scalar(select(Movement).where(Movement.id == application_id, Movement.owner_id == owner, Movement.kind == "APPLICATION"))
    if original is None or investment_id is not None and original.investment_id != investment_id:
        raise LookupError("Application not found")
    db.execute(text("SET LOCAL lock_timeout='5s'"))
    db.execute(text("SELECT pg_advisory_xact_lock(20001,:id)"), {"id": original.investment_id})
    # Lock first, then reread ownership, path, archive state, and immutable source.
    original = db.scalar(select(Movement).where(Movement.id == application_id,
        Movement.investment_id == original.investment_id, Movement.owner_id == owner,
        Movement.kind == "APPLICATION"))
    if original is None:
        raise LookupError("Application not found")
    # Serialize request identities too, including collisions across different contracts.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"fi-revision:{owner}:{data.request_id}"})
    existing = db.scalar(select(ApplicationRevision).where(ApplicationRevision.owner_id == owner, ApplicationRevision.request_id == data.request_id))
    values = dict(application_id=application_id, owner_id=owner, revision=data.expected_revision + 1,
                  **data.model_dump(exclude={"expected_revision"}))
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise ValueError("Idempotency key already used with different content")
        existing._revision_created = False
        return existing
    row = ApplicationRevision(**values)
    db.add(row)
    db.flush()
    # Reload database-normalized NUMERIC(20,8) and trigger-owned fields so the
    # creation response is byte-for-byte equivalent in value shape to a replay.
    db.refresh(row)
    row._revision_created = True
    return row


router = APIRouter(prefix="/api/fixed-income/investments", tags=["application-revisions"])


def _payload(body, key):
    return RevisionInput(**body.model_dump(), request_id=key)


def _safe_revision_error(error):
    if isinstance(error, LookupError):
        raise HTTPException(404, "Aplicação não encontrada")
    if isinstance(error, ValueError):
        raise HTTPException(409, str(error))
    if isinstance(error, DBAPIError):
        sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
        primary = getattr(getattr(getattr(error, "orig", None), "diag", None), "message_primary", "")
        if sqlstate == "23514" and primary in ("Archived contract", "Invalid application or owner"):
            raise HTTPException(404, "Aplicação não encontrada")
        if sqlstate == "23514" and primary == "Stale revision or terminal VOID":
            raise HTTPException(409, "A aplicação foi revisada; atualize o histórico antes de tentar novamente")
        if sqlstate == "23514":
            raise HTTPException(422, "Correção incompatível com a cronologia, abertura, observações ou resgates existentes")
        if sqlstate == "23505":
            raise HTTPException(409, "Conflito de revisão; atualize o histórico e tente novamente")
        if sqlstate in ("55P03", "57014"):
            raise HTTPException(409, "Outro lançamento está sendo processado; repita a solicitação")
    raise error


def _result(db, row):
    return {"id": row.id, "application_id": row.application_id, "revision": row.revision,
        "kind": row.kind, "replacement_date": row.replacement_date,
        "replacement_amount": str(row.replacement_amount) if row.replacement_amount is not None else None,
        "reason": row.reason, "created_at": row.created_at}


@router.post("/{investment_id}/applications/{movement_id}/revisions")
def create_application_revision(investment_id: int, movement_id: int, body: RevisionBody,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    if is_archived(db, investment_id):
        raise HTTPException(404, "Investimento não encontrado")
    try:
        row = append_revision(db, movement_id, _payload(body, idempotency_key), investment_id=investment_id)
        created = row._revision_created
        result = _result(db, row)
        db.commit()
        return Response(content=json.dumps(result, default=str), media_type="application/json", status_code=201 if created else 200)
    except (LookupError, ValueError, DBAPIError) as error:
        db.rollback()
        _safe_revision_error(error)


@router.post("/{investment_id}/applications/{movement_id}/revisions/preview")
def preview_application_revision(investment_id: int, movement_id: int, body: RevisionBody,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    owner = db.info.get("owner_id")
    original = db.scalar(select(Movement).where(Movement.id == movement_id, Movement.investment_id == investment_id,
        Movement.owner_id == owner, Movement.kind == "APPLICATION"))
    if original is None:
        raise HTTPException(404, "Aplicação não encontrada")
    projected = effective_movements(db)
    try:
        db.execute(text("SET LOCAL lock_timeout='5s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(20001,:id)"), {"id": investment_id})
        savepoint = db.begin_nested()
        before = [MovementOutput.model_validate(dict(r)) for r in db.execute(select(projected).where(projected.c.investment_id == investment_id)).mappings()]
        row = append_revision(db, movement_id, _payload(body, idempotency_key), investment_id=investment_id)
        after_rows = db.execute(select(projected).where(projected.c.investment_id == investment_id)).mappings().all()
        after = [MovementOutput.model_validate(dict(r)) for r in after_rows]
        before_balance = principal_balances(before).get(original.lot_id, Decimal(0))
        after_balance = principal_balances(after).get(original.lot_id, Decimal(0))
        result = {"kind": body.kind, "lot_id": original.lot_id, "principal_before": str(before_balance),
            "principal_after": str(after_balance), "effective_date": body.replacement_date if body.kind == "REPLACE" else None,
            "amount": str(body.replacement_amount) if body.kind == "REPLACE" else None,
            "reason": body.reason, "will_create_event": row._revision_created,
            "idempotent_replay": not row._revision_created}
        savepoint.rollback()
        return result
    except (LookupError, ValueError, DBAPIError) as error:
        if db.in_nested_transaction(): db.rollback()
        db.rollback()
        _safe_revision_error(error)


@router.get("/{investment_id}/applications/{movement_id}/revisions")
def list_application_revisions(investment_id: int, movement_id: int,
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    owner = db.info.get("owner_id")
    application = db.scalar(select(Movement.id).where(Movement.id == movement_id, Movement.investment_id == investment_id,
        Movement.owner_id == owner, Movement.kind == "APPLICATION"))
    if application is None:
        raise HTTPException(404, "Aplicação não encontrada")
    rows = db.scalars(select(ApplicationRevision).where(ApplicationRevision.application_id == movement_id,
        ApplicationRevision.owner_id == owner).order_by(ApplicationRevision.revision).offset(offset).limit(limit))
    return [_result(db, row) for row in rows]
