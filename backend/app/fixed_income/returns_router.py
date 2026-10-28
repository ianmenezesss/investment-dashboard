import asyncio
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session
from .projection import effective_movements
from ..access import private_db
from ..bcb_rates.router import rates_service
from ..bcb_rates.schemas import Period, RateError
from .models import Investment, InvestmentArchive, Lot, Movement
from .observations import PositionObservation
from .schemas import InvestmentOutput, MovementOutput, financial_today
from .returns_engine import estimate_returns
from .returns_schemas import ReturnsSnapshot, LotSnapshot, InvestmentReturns, Convention, Calendar, TaxProfile, RatesReference

router = APIRouter(prefix="/api/fixed-income/investments", tags=["fixed-income-returns"])


def returns_snapshot(investment_id: int, db: Session = Depends(private_db)):
    owner = db.info.get("owner_id")
    # A single statement observes contract, lots and events in the same MVCC snapshot.
    projected = effective_movements(db)
    effective = projected.c
    applications = select(projected.c.lot_id, projected.c.date, projected.c.investment_id, projected.c.owner_id).where(projected.c.kind == "APPLICATION").subquery("effective_applications")
    rows = db.execute(select(Investment, Lot, PositionObservation, *projected.c, applications.c.date).select_from(Investment)
        .outerjoin(applications, and_(applications.c.investment_id == Investment.id, applications.c.owner_id == owner))
        .outerjoin(Lot, Lot.id == applications.c.lot_id)
        .outerjoin(projected, and_(effective.lot_id == Lot.id, effective.owner_id == owner))
        .outerjoin(PositionObservation, and_(PositionObservation.investment_id == Investment.id, PositionObservation.kind == 'OPENING', PositionObservation.owner_id == owner))
        .where(Investment.id == investment_id, Investment.owner_id == owner,
            ~exists(select(InvestmentArchive.id).where(InvestmentArchive.investment_id == Investment.id)))
        .order_by(Lot.id, effective.date, effective.id).limit(10001)).all()
    if not rows:
        raise HTTPException(404, "Investimento não encontrado")
    if len(rows) > 10000:
        raise HTTPException(422, "Histórico excede o limite de 10000 registros desta consulta")
    lots, movements = {}, []
    for row in rows:
        lot = row[1]
        if lot is not None:
            lots[lot.id] = LotSnapshot(lot.id, row[-1])
        values = dict(zip(projected.c.keys(), row[3:-1]))
        if values["id"] is not None:
            movements.append(MovementOutput.model_validate(values))
    contract = InvestmentOutput.model_validate(rows[0][0])
    if rows[0][2] is not None:
        contract.tracking_mode = "CONSOLIDATED"
    snapshot = ReturnsSnapshot(contract, tuple(lots.values()),
        tuple(movements), datetime.now(timezone.utc))
    db.rollback()  # release pooled connection before waiting for BCB; objects copied above
    return snapshot


async def collect_cdi(service, start, end):
    points, references = [], []
    try:
        async with asyncio.timeout(30):
            while start < end:
                final = min(start + timedelta(days=365), end - timedelta(days=1))
                period = Period(start_date=start, end_date=final)
                try:
                    response = await service.get(12, period)
                except RateError as error:
                    # At most one short wait for the SGS service's 1s spacing, never
                    # retry upstream errors/429 or override its rolling request budget.
                    if error.code != "local_rate_limited" or error.retry_after > 2:
                        raise
                    await asyncio.sleep(error.retry_after)
                    response = await service.get(12, period)
                points.extend(response.observations)
                references.append(RatesReference(**response.model_dump()))
                start = final + timedelta(days=1)
    except RateError as error:
        return [], references, error.code
    except TimeoutError:
        return [], references, "valuation_deadline_exceeded"
    return points, references, None


@router.get("/{investment_id}/returns", response_model=InvestmentReturns)
async def investment_returns(as_of: date, convention: Convention | None = None,
    calendar: Calendar | None = None, tax_profile: TaxProfile | None = None,
    snapshot: ReturnsSnapshot = Depends(returns_snapshot), service=Depends(rates_service)):
    if not snapshot.contract.application_date <= as_of <= financial_today():
        raise HTTPException(422, "Data de avaliação anterior à aplicação ou futura")
    # No data request unless the explicitly chosen contract assumptions are supported.
    initial = estimate_returns(snapshot, (), as_of=as_of, convention=convention, calendar=calendar, tax_profile=tax_profile)
    eligible = [lot for lot in initial.lots if lot.status == "incomplete_history"]
    points, references, error = [], [], None
    if eligible:
        start = min(lot.application_date for lot in eligible)
        end = max(lot.accrual_end_exclusive for lot in eligible)
        points, references, error = await collect_cdi(service, start, end)
    return estimate_returns(snapshot, points, as_of=as_of, convention=convention, calendar=calendar,
        tax_profile=tax_profile, rates_error=error, references=references)
