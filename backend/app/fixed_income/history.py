"""Dated, declared CDB positions. No interpolation or inferred portfolio total."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from ..access import private_db
from .models import Investment, InvestmentArchive
from .observations import PositionObservation

router = APIRouter(prefix="/api/fixed-income/investments", tags=["fixed-income-history"])


class ObservedPoint(BaseModel):
    as_of: date
    gross_value: Decimal
    net_value: Decimal
    source: str


class ObservedHistory(BaseModel):
    investment_id: int
    coverage: str
    metric: str = "declared_whole_contract_position"
    points: list[ObservedPoint]
    warning: str = "Pontos declarados; sem interpolação, cotações ou soma com lotes. Não é patrimônio total da carteira."


@router.get("/{investment_id}/observed-history", response_model=ObservedHistory)
def observed_history(investment_id: int, start: date = Query(), end: date = Query(),
                     db: Session = Depends(private_db)):
    if start > end or (end - start).days > 3660:
        raise HTTPException(422, "Período inválido ou superior a 10 anos")
    owner = db.info.get("owner_id")
    contract = db.scalar(select(Investment.id).where(
        Investment.id == investment_id, Investment.owner_id == owner,
        ~exists(select(InvestmentArchive.id).where(InvestmentArchive.investment_id == Investment.id))))
    if contract is None:
        raise HTTPException(404, "Investimento não encontrado")
    rows = db.scalars(select(PositionObservation).where(
        PositionObservation.investment_id == investment_id,
        PositionObservation.owner_id == owner,
        PositionObservation.as_of >= start, PositionObservation.as_of <= end,
    ).order_by(PositionObservation.as_of, PositionObservation.id).limit(1001)).all()
    if len(rows) > 1000:
        raise HTTPException(422, "Mais de 1000 observações no período")
    # Same-day revisions are observations, not cumulative values: retain the last declared point.
    points = {row.as_of: ObservedPoint(as_of=row.as_of, gross_value=row.gross_value,
                                      net_value=row.net_value, source=row.source) for row in rows}
    return ObservedHistory(investment_id=investment_id,
                           coverage="observed_points_only" if points else "unavailable",
                           points=list(points.values()))
