"""Owner-scoped, dated observations for prospective portfolio evolution."""
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Numeric, String, Uuid, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .access import private_db
from .auth import authenticate
from .database import Base
from .fixed_income.models import Investment, InvestmentArchive
from .fixed_income.observations import PositionObservation

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
MAX_VALUE = Decimal("999999999999.99")
Money = Annotated[Decimal, Field(ge=0, le=MAX_VALUE, max_digits=14, decimal_places=2, allow_inf_nan=False)]


class PortfolioValuationObservation(Base):
    __tablename__ = "portfolio_valuation_observations"
    __table_args__ = (
        CheckConstraint("equities_market_value IS NULL OR (equities_market_value >= 0 AND equities_market_value <= 999999999999.99)", name="pvo_equities_value"),
        CheckConstraint("(equities_market_value IS NULL AND equities_source IS NULL) OR (equities_market_value IS NOT NULL AND equities_source IS NOT NULL AND length(trim(equities_source)) BETWEEN 1 AND 240)", name="pvo_equities_source"),
        CheckConstraint("(fixed_income_gross_value IS NULL AND fixed_income_net_value IS NULL) OR (fixed_income_gross_value IS NOT NULL AND fixed_income_net_value IS NOT NULL AND fixed_income_net_value >= 0 AND fixed_income_net_value <= fixed_income_gross_value AND fixed_income_gross_value <= 999999999999.99)", name="pvo_fixed_income_values"),
        CheckConstraint("fixed_income_coverage IN ('complete','partial','unavailable','empty')", name="pvo_fixed_income_coverage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    equities_market_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    equities_source: Mapped[str | None] = mapped_column(String(240), nullable=True)
    fixed_income_gross_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    fixed_income_net_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    fixed_income_coverage: Mapped[str] = mapped_column(String(16))
    fixed_income_sources: Mapped[list] = mapped_column(JSON, default=list)
    missing_fixed_income: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PortfolioObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    as_of: date
    equities_market_value: Money
    equities_source: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_observation(self):
        if not self.equities_source.strip():
            raise ValueError("Informe a origem do valor de ações")
        if self.as_of > datetime.now(LOCAL_TZ).date():
            raise ValueError("A data-base não pode ser futura")
        return self


class PortfolioObservationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    as_of: date
    equities_market_value: Decimal | None
    equities_source: str | None
    fixed_income_gross_value: Decimal | None
    fixed_income_net_value: Decimal | None
    fixed_income_coverage: Literal["complete", "partial", "unavailable", "empty"]
    fixed_income_sources: list[dict[str, str]]
    missing_fixed_income: list[str]
    consolidated_gross_value: Decimal | None
    consolidated_net_value: Decimal | None
    consolidated_coverage: Literal["complete", "partial"]
    created_at: datetime


router = APIRouter(prefix="/api/dashboard", tags=["wealth-observations"], dependencies=[Depends(authenticate)])


def _owner_filter(owner):
    return PortfolioValuationObservation.owner_id.is_(None) if owner is None else PortfolioValuationObservation.owner_id == owner


def _output(row: PortfolioValuationObservation) -> PortfolioObservationOutput:
    cdb_complete = row.fixed_income_coverage in ("complete", "empty")
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    total_gross = total_net = None
    if row.equities_market_value is not None and cdb_complete:
        with localcontext() as ctx:
            ctx.prec = 64
            gross = row.fixed_income_gross_value or Decimal(0)
            net = row.fixed_income_net_value or Decimal(0)
            total_gross = row.equities_market_value + gross
            total_net = row.equities_market_value + net
    return PortfolioObservationOutput(
        id=row.id, as_of=row.as_of, equities_market_value=row.equities_market_value,
        equities_source=row.equities_source, fixed_income_gross_value=row.fixed_income_gross_value,
        fixed_income_net_value=row.fixed_income_net_value, fixed_income_coverage=row.fixed_income_coverage,
        fixed_income_sources=row.fixed_income_sources or [], missing_fixed_income=row.missing_fixed_income or [],
        consolidated_gross_value=total_gross, consolidated_net_value=total_net,
        consolidated_coverage="complete" if total_net is not None else "partial", created_at=created_at,
    )


def _fixed_income_on_date(db: Session, owner, as_of: date):
    investments = list(db.scalars(select(Investment).where(
        Investment.owner_id.is_(None) if owner is None else Investment.owner_id == owner,
        ~exists(select(InvestmentArchive.id).where(InvestmentArchive.investment_id == Investment.id)),
    ).order_by(Investment.id)))
    if not investments:
        return Decimal(0), Decimal(0), "empty", [], []
    latest_by_investment = {}
    observations = db.scalars(select(PositionObservation).where(
        (PositionObservation.owner_id.is_(None) if owner is None else PositionObservation.owner_id == owner),
        PositionObservation.as_of == as_of,
        PositionObservation.investment_id.in_([item.id for item in investments]),
    ).order_by(PositionObservation.investment_id, PositionObservation.id))
    for observation in observations:
        latest_by_investment[observation.investment_id] = observation
    missing, sources = [], []
    gross_total = net_total = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 64
        for investment in investments:
            observation = latest_by_investment.get(investment.id)
            if observation is None:
                missing.append(investment.product_name)
                continue
            gross_total += observation.gross_value
            net_total += observation.net_value
            sources.append({"asset": investment.product_name, "source": observation.source})
    coverage = "complete" if not missing else "partial" if sources else "unavailable"
    return gross_total if sources else None, net_total if sources else None, coverage, sources, missing


@router.get("/wealth-observations", response_model=list[PortfolioObservationOutput])
def list_wealth_observations(db: Session = Depends(private_db)):
    owner = db.info.get("owner_id")
    rows = list(db.scalars(select(PortfolioValuationObservation).where(_owner_filter(owner))
        .order_by(PortfolioValuationObservation.as_of.desc(), PortfolioValuationObservation.id.desc()).limit(5000)))
    latest_by_date = {}
    for row in rows:
        latest_by_date.setdefault(row.as_of, row)
    return [_output(latest_by_date[day]) for day in sorted(latest_by_date)]


@router.post("/wealth-observations", status_code=201, response_model=PortfolioObservationOutput)
def create_wealth_observation(
    data: PortfolioObservationInput, response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), db: Session = Depends(private_db),
):
    owner = db.info.get("owner_id")
    existing = db.scalar(select(PortfolioValuationObservation).where(
        PortfolioValuationObservation.request_id == idempotency_key))
    if existing is not None:
        if (existing.owner_id != owner or existing.as_of != data.as_of
                or existing.equities_market_value != data.equities_market_value
                or existing.equities_source != data.equities_source):
            raise HTTPException(409, "Chave de idempotência já utilizada")
        response.status_code = 200
        return _output(existing)
    gross, net, coverage, sources, missing = _fixed_income_on_date(db, owner, data.as_of)
    row = PortfolioValuationObservation(owner_id=owner, request_id=idempotency_key, as_of=data.as_of,
        equities_market_value=data.equities_market_value, equities_source=data.equities_source,
        fixed_income_gross_value=gross, fixed_income_net_value=net, fixed_income_coverage=coverage,
        fixed_income_sources=sources, missing_fixed_income=missing)
    try:
        db.add(row)
        db.flush()
        payload = _output(row)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Não foi possível registrar a observação; atualize o histórico e tente novamente") from None
    return payload
