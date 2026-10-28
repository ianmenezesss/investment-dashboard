from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..access import private_db
from .router import is_archived, owned_investment
from .observations import PositionObservation, ObservationInput, ObservationOutput, observation_query, validate_observation

router = APIRouter(prefix="/api/fixed-income/investments", tags=["manual-positions"])


def save_observation(investment_id, data, kind, db):
    investment = owned_investment(db, investment_id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='5s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(20001,:id)"), {"id": investment_id})
    if is_archived(db, investment_id):
        raise HTTPException(404, "Investimento não encontrado")
    validate_observation(db, investment, data, kind)
    row = PositionObservation(**data.model_dump(), kind=kind, investment_id=investment_id, owner_id=db.info.get("owner_id"))
    db.add(row); db.flush()
    result = ObservationOutput.model_validate(row)
    db.commit()
    return result


@router.post("/{investment_id}/opening-balance", status_code=201, response_model=ObservationOutput)
def create_opening(investment_id: int, data: ObservationInput, db: Session = Depends(private_db)):
    return save_observation(investment_id, data, "OPENING", db)


@router.post("/{investment_id}/observations", status_code=201, response_model=ObservationOutput)
def create_observation(investment_id: int, data: ObservationInput, db: Session = Depends(private_db)):
    return save_observation(investment_id, data, "OBSERVATION", db)


@router.get("/{investment_id}/observations", response_model=list[ObservationOutput])
def list_observations(investment_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    return list(db.scalars(observation_query(db, investment_id).order_by(PositionObservation.as_of, PositionObservation.id).offset(offset).limit(limit)))
