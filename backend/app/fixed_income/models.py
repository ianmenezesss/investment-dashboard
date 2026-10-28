from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Investment(Base):
    __tablename__ = "fixed_income_investments"
    __table_args__ = (
        CheckConstraint("product_type = 'CDB'", name="fi_product_supported"),
        CheckConstraint("(remuneration = 'FIXED' AND indexer = 'NONE') OR (remuneration = 'CDI' AND indexer = 'CDI')", name="fi_rate_pair"),
        CheckConstraint("contracted_rate > 0 AND contracted_rate < 10000", name="fi_rate_positive"),
        CheckConstraint("maturity_date > application_date", name="fi_maturity"),
        CheckConstraint("length(trim(issuer)) > 0 AND length(trim(product_name)) > 0", name="fi_names"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    issuer: Mapped[str] = mapped_column(String(160))
    product_name: Mapped[str] = mapped_column(String(160))
    product_type: Mapped[str] = mapped_column(String(20))
    remuneration: Mapped[str] = mapped_column(String(20))
    indexer: Mapped[str] = mapped_column(String(20))
    contracted_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    application_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Lot(Base):
    __tablename__ = "fixed_income_lots"
    __table_args__ = (UniqueConstraint("id", "investment_id", name="fi_lot_investment_unique"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_investments.id"), index=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    application_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Movement(Base):
    __tablename__ = "fixed_income_movements"
    __table_args__ = (
        ForeignKeyConstraint(["lot_id", "investment_id"], ["fixed_income_lots.id", "fixed_income_lots.investment_id"], name="fi_movement_lot_fk"),
        CheckConstraint("kind IN ('APPLICATION', 'REDEMPTION')", name="fi_movement_kind"),
        CheckConstraint("principal_amount > 0 AND principal_amount <= 999999999999.99999999", name="fi_principal_positive"),
        CheckConstraint("cash_received IS NULL OR (kind = 'REDEMPTION' AND cash_received >= 0 AND cash_received <= 999999999999.99999999)", name="fi_cash_redemption"),
        Index("fi_one_application_per_lot", "lot_id", unique=True,
              postgresql_where=text("kind = 'APPLICATION'"), sqlite_where=text("kind = 'APPLICATION'")),
        Index("ix_fi_movements_chronology", "investment_id", "date", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_investments.id"))
    lot_id: Mapped[int] = mapped_column(index=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cash_received: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InvestmentArchive(Base):
    """Append-only tombstone; original contract and financial rows remain intact."""
    __tablename__ = "fixed_income_investment_archives"
    __table_args__ = (UniqueConstraint("investment_id", name="fi_one_archive_per_investment"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    investment_id: Mapped[int] = mapped_column(ForeignKey("fixed_income_investments.id", ondelete="RESTRICT"), nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
