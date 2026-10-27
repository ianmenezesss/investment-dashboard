from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Date, DateTime, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(4))
    date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
