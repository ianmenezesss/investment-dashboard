"""Manual whole-contract observations, never ledger deposits or inferred principal."""
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from typing import Literal, Annotated
from zoneinfo import ZoneInfo
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, select, text, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class PositionObservation(Base):
    __tablename__ = "fixed_income_observations"
    __table_args__ = (
        CheckConstraint("kind IN ('OPENING','OBSERVATION')", name="fi_observation_kind"),
        CheckConstraint("reason IN ('POSITION','AFTER_CONSOLIDATED_REDEMPTION')", name="fi_observation_reason"),
        CheckConstraint("net_value <= gross_value", name="fi_observation_net"),
        CheckConstraint("taxes_combined IS NULL OR (ir_estimate IS NULL AND iof_estimate IS NULL)", name="fi_observation_tax_mode"),
        CheckConstraint("taxes_combined IS NULL OR gross_value-net_value=taxes_combined", name="fi_observation_tax_total"),
        CheckConstraint("ir_estimate IS NULL OR iof_estimate IS NULL OR gross_value-net_value=ir_estimate+iof_estimate", name="fi_observation_tax_parts"),
        CheckConstraint("coalesce(ir_estimate,0)+coalesce(iof_estimate,0)<=gross_value-net_value", name="fi_observation_tax_known"),
        CheckConstraint("(kind <> 'OPENING' OR reason='POSITION') AND (cash_received IS NULL OR (kind='OBSERVATION' AND reason='AFTER_CONSOLIDATED_REDEMPTION'))", name="fi_observation_cash"),
        CheckConstraint("length(trim(source))>0", name="fi_observation_source"),
        *[CheckConstraint(f"{field} IS NULL OR ({field}>=0 AND {field}<=999999999999.99)", name=f"fi_obs_{field}_valid") for field in ("gross_value", "net_value", "ir_estimate", "iof_estimate", "taxes_combined", "confirmed_principal", "cash_received")],
        CheckConstraint("reported_gain IS NULL OR (reported_gain>=-999999999999.99 AND reported_gain<=999999999999.99)", name="fi_observation_gain"),
        Index("fi_one_opening_per_investment", "investment_id", unique=True, postgresql_where=text("kind='OPENING'"), sqlite_where=text("kind='OPENING'")),
        Index("ix_fi_observation_chronology", "investment_id", "as_of", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_investments.id"))
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[date] = mapped_column(Date)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    net_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    ir_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    iof_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    taxes_combined: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    reported_gain: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    confirmed_principal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cash_received: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    as_of: date
    gross_value: Money
    net_value: Money
    ir_estimate: Money | None = None
    iof_estimate: Money | None = None
    taxes_combined: Money | None = None
    reported_gain: Decimal | None = Field(default=None, max_digits=14, decimal_places=2, allow_inf_nan=False)
    confirmed_principal: Money | None = None
    reason: Literal["POSITION", "AFTER_CONSOLIDATED_REDEMPTION"] = "POSITION"
    cash_received: Money | None = None
    source: str = Field(min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def consistent(self):
        if self.as_of > datetime.now(ZoneInfo("America/Sao_Paulo")).date():
            raise ValueError("A data-base não pode ser futura")
        with localcontext() as ctx:
            ctx.prec = 64
            difference = self.gross_value - self.net_value
            if difference < 0:
                raise ValueError("Patrimônio líquido não pode superar o bruto")
            if self.taxes_combined is not None:
                if self.ir_estimate is not None or self.iof_estimate is not None:
                    raise ValueError("Informe tributos combinados ou IR/IOF discriminados, nunca ambos")
                if difference != self.taxes_combined:
                    raise ValueError("Bruto menos tributos combinados deve ser igual ao líquido")
            known = (self.ir_estimate or Decimal(0)) + (self.iof_estimate or Decimal(0))
            if known > difference or self.ir_estimate is not None and self.iof_estimate is not None and known != difference:
                raise ValueError("IR/IOF informados são inconsistentes com bruto e líquido")
        if self.cash_received is not None and self.reason != "AFTER_CONSOLIDATED_REDEMPTION":
            raise ValueError("Caixa de resgate exige conciliação após resgate consolidado")
        with localcontext() as ctx:
            ctx.prec = 64
            for field in ("gross_value", "net_value", "ir_estimate", "iof_estimate", "taxes_combined", "reported_gain", "confirmed_principal", "cash_received"):
                value = getattr(self, field)
                if value is not None:
                    setattr(self, field, value.quantize(Decimal("0.01")))
        return self


class ObservationOutput(ObservationInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    investment_id: int
    kind: Literal["OPENING", "OBSERVATION"]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def observation_query(db, investment_id):
    return select(PositionObservation).where(PositionObservation.investment_id == investment_id,
        PositionObservation.owner_id == db.info.get("owner_id"))


def opening(db, investment_id):
    return db.scalar(observation_query(db, investment_id).where(PositionObservation.kind == "OPENING"))


def latest(db, investment_id):
    return db.scalar(observation_query(db, investment_id).order_by(PositionObservation.as_of.desc(), PositionObservation.id.desc()).limit(1))


def validate_observation(db, investment, data, kind):
    from .models import Movement, Lot
    from fastapi import HTTPException
    if data.as_of < investment.application_date:
        raise HTTPException(422, "Data-base anterior à data inicial do contrato")
    start = opening(db, investment.id)
    if kind == "OPENING":
        if start:
            raise HTTPException(409, "Acompanhamento com saldo atual já foi iniciado")
        if db.scalar(select(Lot.id).where(Lot.investment_id == investment.id, Lot.owner_id == db.info.get("owner_id")).limit(1)) is not None:
            raise HTTPException(409, "Contrato já possui lotes; preserve o histórico existente, sem adicionar saldo inicial")
        if data.reason != "POSITION" or data.cash_received is not None:
            raise HTTPException(422, "Abertura não registra resgate")
    elif not start:
        raise HTTPException(409, "Inicie o acompanhamento com saldo atual antes de conciliar")
    previous = latest(db, investment.id)
    from .projection import effective_movements
    effective = effective_movements(db)
    last_movement = db.scalar(select(func.max(effective.c.date)).where(effective.c.investment_id == investment.id, effective.c.owner_id == db.info.get("owner_id")))
    if previous and data.as_of < previous.as_of or last_movement and data.as_of < last_movement:
        raise HTTPException(422, "Observações devem seguir a cronologia das posições e movimentações")
