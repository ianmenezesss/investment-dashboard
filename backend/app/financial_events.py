"""Private, manually observed portfolio events with append-only corrections."""
from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, Uuid, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .access import private_db
from .auth import authenticate
from .database import Base

ZERO = Decimal("0")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
EVENT_KINDS = ("CONTRIBUTION", "WITHDRAWAL", "DIVIDEND", "JCP", "CORPORATE_ACTION")
MONEY_MAX = Decimal("999999999999.99999999")
TICKER_PATTERN = r"^[A-Z0-9]{4,20}$"


class FinancialEvent(Base):
    __tablename__ = "financial_events"
    __table_args__ = (
        CheckConstraint("kind IN ('CONTRIBUTION','WITHDRAWAL','DIVIDEND','JCP','CORPORATE_ACTION')", name="financial_event_kind"),
        CheckConstraint("length(trim(source)) BETWEEN 1 AND 240", name="financial_event_source"),
        CheckConstraint("((kind IN ('CONTRIBUTION','WITHDRAWAL') AND ticker IS NULL AND cash_amount IS NOT NULL AND cash_amount > 0 AND gross_amount IS NULL AND tax_withheld IS NULL AND description IS NULL) OR (kind IN ('DIVIDEND','JCP') AND ticker IS NOT NULL AND cash_amount IS NOT NULL AND cash_amount > 0 AND (gross_amount IS NULL OR gross_amount > 0) AND (tax_withheld IS NULL OR tax_withheld >= 0) AND description IS NULL AND (gross_amount IS NULL OR tax_withheld IS NULL OR gross_amount-tax_withheld=cash_amount)) OR (kind='CORPORATE_ACTION' AND ticker IS NOT NULL AND cash_amount IS NULL AND gross_amount IS NULL AND tax_withheld IS NULL AND description IS NOT NULL AND length(trim(description)) > 0))", name="financial_event_payload"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    event_date: Mapped[date] = mapped_column(Date)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    tax_withheld: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    source: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FinancialEventRevision(Base):
    __tablename__ = "financial_event_revisions"
    __table_args__ = (
        UniqueConstraint("event_id", "revision", name="financial_event_revision_number"),
        CheckConstraint("kind IN ('REPLACE','VOID')", name="financial_event_revision_kind"),
        CheckConstraint("revision > 0 AND length(trim(reason)) BETWEEN 1 AND 1000", name="financial_event_revision_metadata"),
        CheckConstraint("(kind='VOID' AND replacement_kind IS NULL AND replacement_date IS NULL AND replacement_ticker IS NULL AND replacement_cash_amount IS NULL AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_source IS NULL AND replacement_description IS NULL) OR (kind='REPLACE' AND replacement_kind IS NOT NULL AND replacement_date IS NOT NULL AND replacement_source IS NOT NULL AND length(trim(replacement_source)) BETWEEN 1 AND 240 AND ((replacement_kind IN ('CONTRIBUTION','WITHDRAWAL') AND replacement_ticker IS NULL AND replacement_cash_amount IS NOT NULL AND replacement_cash_amount > 0 AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_description IS NULL) OR (replacement_kind IN ('DIVIDEND','JCP') AND replacement_ticker IS NOT NULL AND replacement_cash_amount IS NOT NULL AND replacement_cash_amount > 0 AND (replacement_gross_amount IS NULL OR replacement_gross_amount > 0) AND (replacement_tax_withheld IS NULL OR replacement_tax_withheld >= 0) AND replacement_description IS NULL AND (replacement_gross_amount IS NULL OR replacement_tax_withheld IS NULL OR replacement_gross_amount-replacement_tax_withheld=replacement_cash_amount)) OR (replacement_kind='CORPORATE_ACTION' AND replacement_ticker IS NOT NULL AND replacement_cash_amount IS NULL AND replacement_gross_amount IS NULL AND replacement_tax_withheld IS NULL AND replacement_description IS NOT NULL AND length(trim(replacement_description)) > 0)))", name="financial_event_revision_payload"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("financial_events.id"), index=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    revision: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(8))
    replacement_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    replacement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    replacement_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    replacement_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    replacement_gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    replacement_tax_withheld: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    replacement_source: Mapped[str | None] = mapped_column(String(240), nullable=True)
    replacement_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reason: Mapped[str] = mapped_column(String(1000))
    request_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["CONTRIBUTION", "WITHDRAWAL", "DIVIDEND", "JCP", "CORPORATE_ACTION"]
    event_date: date
    ticker: str | None = Field(default=None, pattern=TICKER_PATTERN)
    cash_amount: Decimal | None = Field(default=None, gt=0, le=MONEY_MAX, max_digits=20, decimal_places=8, allow_inf_nan=False)
    gross_amount: Decimal | None = Field(default=None, gt=0, le=MONEY_MAX, max_digits=20, decimal_places=8, allow_inf_nan=False)
    tax_withheld: Decimal | None = Field(default=None, ge=0, le=MONEY_MAX, max_digits=20, decimal_places=8, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_event(self):
        if not self.source.strip():
            raise ValueError("Informe a origem observada do lançamento")
        if self.kind in ("CONTRIBUTION", "WITHDRAWAL"):
            if self.ticker is not None or self.cash_amount is None or self.gross_amount is not None or self.tax_withheld is not None or self.description is not None:
                raise ValueError("Aporte/retirada exige somente valor em caixa, data e origem")
        elif self.kind in ("DIVIDEND", "JCP"):
            if self.ticker is None or self.cash_amount is None or self.description is not None:
                raise ValueError("Provento exige ativo e valor recebido registrado")
            if self.gross_amount is not None and self.tax_withheld is not None and self.gross_amount - self.tax_withheld != self.cash_amount:
                raise ValueError("Valor recebido deve corresponder ao bruto menos o imposto informado")
        else:
            if self.ticker is None or self.cash_amount is not None or self.gross_amount is not None or self.tax_withheld is not None or not (self.description or "").strip():
                raise ValueError("Evento societário exige ativo, descrição e origem, sem valor financeiro inferido")
        return self


class EventRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["REPLACE", "VOID"]
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    replacement: EventInput | None = None

    @model_validator(mode="after")
    def payload(self):
        if not self.reason.strip() or (self.kind == "REPLACE") != (self.replacement is not None):
            raise ValueError("Substituição exige novos dados; anulação não aceita payload financeiro")
        return self


class CsvImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int = Field(ge=1)
    event: EventInput


class CsvImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[CsvImportRow] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_rows(self):
        if len({item.row_number for item in self.rows}) != len(self.rows):
            raise ValueError("Número de linha duplicado no lote")
        return self


def _today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _owner_filter(model, owner):
    return model.owner_id.is_(None) if owner is None else model.owner_id == owner


def _raw_event(row):
    return {"id": row.id, "kind": row.kind, "event_date": row.event_date,
        "ticker": row.ticker, "cash_amount": row.cash_amount, "gross_amount": row.gross_amount,
        "tax_withheld": row.tax_withheld, "source": row.source, "description": row.description,
        "revision": 0, "owner_id": row.owner_id, "created_at": row.created_at}


def effective_events(db: Session, owner_id):
    events = list(db.scalars(select(FinancialEvent).where(_owner_filter(FinancialEvent, owner_id))))
    revisions = list(db.scalars(select(FinancialEventRevision).where(
        _owner_filter(FinancialEventRevision, owner_id)).order_by(FinancialEventRevision.event_id, FinancialEventRevision.revision)))
    latest = {}
    for row in revisions:
        latest[row.event_id] = row
    result = []
    for original in events:
        current = _raw_event(original)
        revision = latest.get(original.id)
        if revision is not None:
            if revision.kind == "VOID":
                continue
            current.update({"kind": revision.replacement_kind, "event_date": revision.replacement_date,
                "ticker": revision.replacement_ticker, "cash_amount": revision.replacement_cash_amount,
                "gross_amount": revision.replacement_gross_amount, "tax_withheld": revision.replacement_tax_withheld,
                "source": revision.replacement_source, "description": revision.replacement_description,
                "revision": revision.revision})
        result.append(current)
    return sorted(result, key=lambda row: (row["event_date"], row["id"]))


def _serialize_event(row):
    return {key: str(value) if isinstance(value, Decimal) else value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in row.items() if key != "owner_id"}


def _event_values(data: EventInput):
    return data.model_dump()


def _import_fingerprint(event):
    """Conservative duplicate key: same observed financial facts, regardless of source label."""
    def canonical(value):
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        return value.isoformat() if isinstance(value, date) else value
    base = tuple(canonical(event.get(key)) for key in ("kind", "event_date", "ticker", "cash_amount"))
    # The generic CSV contract imports only net cash. Gross/tax data may already exist
    # on a manually entered dividend and must not make that same receipt look new.
    return base + ((canonical(event.get("description")),) if event.get("kind") == "CORPORATE_ACTION" else ())


def append_event(db: Session, owner_id, request_id: UUID, data: EventInput):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"financial-event-request:{owner_id}:{request_id}"})
    existing = db.scalar(select(FinancialEvent).where(FinancialEvent.request_id == request_id))
    values = _event_values(data)
    if existing is not None:
        if existing.owner_id != owner_id or any(getattr(existing, key) != value for key, value in values.items()):
            raise ValueError("Chave de idempotência já utilizada")
        existing._event_created = False
        return existing
    row = FinancialEvent(owner_id=owner_id, request_id=request_id, **values)
    db.add(row)
    db.flush()
    row._event_created = True
    return row


def append_event_revision(db: Session, owner_id, event_id: int, data: EventRevisionInput, request_id: UUID):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"financial-event-revision-request:{owner_id}:{request_id}"})
    existing_request = db.scalar(select(FinancialEventRevision).where(FinancialEventRevision.request_id == request_id))
    replacement = data.replacement
    replacement_values = replacement.model_dump() if replacement else {}
    replacement_columns = {f"replacement_{'date' if key == 'event_date' else key}": value
        for key, value in replacement_values.items()}
    expected = {"event_id": event_id, "owner_id": owner_id, "revision": data.expected_revision + 1,
        "kind": data.kind, "reason": data.reason, **replacement_columns}
    if existing_request is not None:
        expected["request_id"] = request_id
        if any(getattr(existing_request, key) != value for key, value in expected.items()):
            raise ValueError("Chave de idempotência já utilizada")
        existing_request._revision_created = False
        return existing_request

    original = db.scalar(select(FinancialEvent).where(
        FinancialEvent.id == event_id, _owner_filter(FinancialEvent, owner_id)))
    if original is None:
        raise LookupError("Lançamento não encontrado")
    if db.bind.dialect.name == "postgresql":
        # Keep API serialization on the same database lock used by the revision trigger,
        # including any insert performed directly through the restricted runtime role.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": str(event_id)})
    revisions = list(db.scalars(select(FinancialEventRevision).where(
        FinancialEventRevision.event_id == event_id, _owner_filter(FinancialEventRevision, owner_id)
    ).order_by(FinancialEventRevision.revision)))
    current = revisions[-1] if revisions else None
    current_revision = current.revision if current else 0
    if current is not None and current.kind == "VOID":
        raise ValueError("Lançamento já anulado")
    if data.expected_revision != current_revision:
        raise ValueError("Lançamento foi alterado; atualize o histórico")
    values = {"event_id": event_id, "owner_id": owner_id, "revision": current_revision + 1,
        "kind": data.kind, "reason": data.reason, "request_id": request_id}
    values.update(replacement_columns)
    row = FinancialEventRevision(**values)
    db.add(row)
    db.flush()
    row._revision_created = True
    return row


def summarize_events(events, *, start: date, end: date):
    totals = defaultdict(lambda: ZERO)
    selected = [row for row in events if start <= row["event_date"] <= end]
    with localcontext() as ctx:
        ctx.prec = 64
        for row in selected:
            if row["kind"] in ("CONTRIBUTION", "WITHDRAWAL", "DIVIDEND", "JCP"):
                totals[row["kind"]] += row["cash_amount"] or ZERO
    return {"period_start": start.isoformat() if start != date.min else None,
        "period_end": end.isoformat(), "coverage": "available" if selected else "empty",
        "contributions": str(totals["CONTRIBUTION"]), "withdrawals": str(totals["WITHDRAWAL"]),
        "net_external_cash_flow": str(totals["CONTRIBUTION"] - totals["WITHDRAWAL"]),
        "dividends_received": str(totals["DIVIDEND"]), "jcp_received": str(totals["JCP"]),
        "income_total_received": str(totals["DIVIDEND"] + totals["JCP"]),
        "event_count": len(selected)}


router = APIRouter(tags=["financial-events"])


@router.get("/api/financial-events", dependencies=[Depends(authenticate)])
def list_financial_events(db: Session = Depends(private_db)):
    return [_serialize_event(row) for row in effective_events(db, db.info.get("owner_id"))]


@router.post("/api/financial-events", status_code=201, dependencies=[Depends(authenticate)])
def create_financial_event(data: EventInput, response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db)):
    if data.event_date > _today():
        raise HTTPException(422, "Data do lançamento não pode ser futura")
    try:
        row = append_event(db, db.info.get("owner_id"), idempotency_key, data)
        created = row._event_created
        result = _serialize_event(_raw_event(row))
        db.commit()
        response.status_code = 201 if created else 200
        return result
    except (ValueError, IntegrityError) as error:
        db.rollback()
        raise HTTPException(409, "Conflito no lançamento; atualize o histórico e tente novamente") from error


@router.post("/api/financial-events/import", status_code=201, dependencies=[Depends(authenticate)])
def import_financial_events(data: CsvImportInput, response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db)):
    """Validate and append a CSV batch atomically; rows already present are reported and skipped."""
    today = _today()
    if any(item.event.event_date > today for item in data.rows):
        raise HTTPException(422, "A importação contém data futura")

    owner = db.info.get("owner_id")
    imported, duplicates = [], []
    try:
        seen_in_batch = set()
        for item in data.rows:
            event = item.event
            values = _event_values(event)
            fingerprint = _import_fingerprint(values)
            # Serialize matching imports in PostgreSQL so concurrent uploads cannot both pass the check.
            if db.bind.dialect.name == "postgresql":
                lock_key = f"financial-event-import:{owner}:{fingerprint!r}"
                db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": lock_key})
            current = {_import_fingerprint(row) for row in effective_events(db, owner)}
            if fingerprint in current or fingerprint in seen_in_batch:
                duplicates.append({"row_number": item.row_number})
                continue
            request_id = uuid5(idempotency_key, f"{owner}:{item.row_number}")
            row = append_event(db, owner, request_id, event)
            imported.append(_serialize_event(_raw_event(row)))
            seen_in_batch.add(fingerprint)
        db.commit()
        response.status_code = 201 if imported else 200
        return {"imported": imported, "duplicates": duplicates,
            "imported_count": len(imported), "duplicate_count": len(duplicates)}
    except (ValueError, IntegrityError) as error:
        db.rollback()
        raise HTTPException(409, "Conflito na importação; nenhuma linha foi gravada. Atualize o histórico e revise o arquivo") from error


@router.get("/api/financial-events/{event_id}/revisions", dependencies=[Depends(authenticate)])
def list_financial_event_revisions(event_id: int, db: Session = Depends(private_db)):
    owner = db.info.get("owner_id")
    exists = db.scalar(select(FinancialEvent.id).where(FinancialEvent.id == event_id, _owner_filter(FinancialEvent, owner)))
    if exists is None:
        raise HTTPException(404, "Lançamento não encontrado")
    rows = db.scalars(select(FinancialEventRevision).where(
        FinancialEventRevision.event_id == event_id, _owner_filter(FinancialEventRevision, owner)
    ).order_by(FinancialEventRevision.revision))
    return [{"id": row.id, "event_id": row.event_id, "revision": row.revision, "kind": row.kind,
        "reason": row.reason, "replacement_kind": row.replacement_kind,
        "replacement_date": row.replacement_date.isoformat() if row.replacement_date else None,
        "replacement_ticker": row.replacement_ticker,
        "replacement_cash_amount": str(row.replacement_cash_amount) if row.replacement_cash_amount is not None else None,
        "replacement_gross_amount": str(row.replacement_gross_amount) if row.replacement_gross_amount is not None else None,
        "replacement_tax_withheld": str(row.replacement_tax_withheld) if row.replacement_tax_withheld is not None else None,
        "replacement_source": row.replacement_source, "replacement_description": row.replacement_description,
        "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/api/financial-events/{event_id}/revisions", dependencies=[Depends(authenticate)])
def revise_financial_event(event_id: int, data: EventRevisionInput, response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db)):
    if data.replacement and data.replacement.event_date > _today():
        raise HTTPException(422, "Data do lançamento não pode ser futura")
    try:
        row = append_event_revision(db, db.info.get("owner_id"), event_id, data, idempotency_key)
        created = row._revision_created
        result = {"id": row.id, "event_id": row.event_id, "revision": row.revision,
            "kind": row.kind, "reason": row.reason,
            "replacement_kind": row.replacement_kind,
            "replacement_date": row.replacement_date.isoformat() if row.replacement_date else None,
            "replacement_ticker": row.replacement_ticker,
            "replacement_cash_amount": str(row.replacement_cash_amount) if row.replacement_cash_amount is not None else None,
            "replacement_gross_amount": str(row.replacement_gross_amount) if row.replacement_gross_amount is not None else None,
            "replacement_tax_withheld": str(row.replacement_tax_withheld) if row.replacement_tax_withheld is not None else None,
            "replacement_source": row.replacement_source, "replacement_description": row.replacement_description}
        db.commit()
        response.status_code = 201 if created else 200
        return result
    except LookupError as error:
        db.rollback()
        raise HTTPException(404, "Lançamento não encontrado") from error
    except (ValueError, IntegrityError) as error:
        db.rollback()
        raise HTTPException(409, "Conflito na revisão; atualize o histórico e tente novamente") from error


@router.get("/api/dashboard/financial-events/summary", dependencies=[Depends(authenticate)])
def financial_event_summary(period: str = Query("Tudo", pattern="^(1M|3M|6M|1A|Tudo)$"), db: Session = Depends(private_db)):
    today = _today()
    months = {"1M": 1, "3M": 3, "6M": 6, "1A": 12}.get(period)
    if months:
        month_index = today.year * 12 + today.month - 1 - months
        year, month = divmod(month_index, 12)
        month += 1
        start = date(year, month, min(today.day, monthrange(year, month)[1]))
    else:
        start = date.min
    return summarize_events(effective_events(db, db.info.get("owner_id")), start=start, end=today)
