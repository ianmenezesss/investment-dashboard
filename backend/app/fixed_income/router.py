from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from ..access import private_db
from .models import Investment, Lot, Movement
from .schemas import InvestmentInput, InvestmentOutput, InvestmentDetail, LotOutput, ApplicationInput, RedemptionInput, MovementOutput
from .ledger import principal_balances, total_principal

router = APIRouter(prefix="/api/fixed-income", tags=["fixed-income"])


def owned_investment(db, investment_id):
    investment = db.scalar(select(Investment).where(Investment.id == investment_id, Investment.owner_id == db.info.get("owner_id")))
    if investment is None:
        raise HTTPException(404, "Investimento não encontrado")
    return investment


def history(db, investment_id):
    return list(db.scalars(select(Movement).where(Movement.investment_id == investment_id,
        Movement.owner_id == db.info.get("owner_id")).order_by(Movement.date, Movement.id)))


def locked_history(db, investment_id, event_date):
    # Same transaction-scoped advisory lock as migration 003; no UPDATE grants needed.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(20001, :id)"), {"id": investment_id})
    movements = history(db, investment_id)
    if movements and event_date < movements[-1].date:
        raise HTTPException(422, "Movimentações devem seguir ordem cronológica por investimento")
    return movements


@router.post("/investments", status_code=201, response_model=InvestmentOutput)
def create_investment(data: InvestmentInput, db: Session = Depends(private_db)):
    investment = Investment(**data.model_dump(), owner_id=db.info.get("owner_id"))
    db.add(investment)
    db.flush()
    payload = InvestmentOutput.model_validate(investment)
    db.commit()
    return payload


@router.get("/investments", response_model=list[InvestmentOutput])
def list_investments(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), db: Session = Depends(private_db)):
    return list(db.scalars(select(Investment).where(Investment.owner_id == db.info.get("owner_id"))
        .order_by(Investment.id).offset(offset).limit(limit)))


@router.get("/investments/{investment_id}", response_model=InvestmentDetail)
def investment_detail(investment_id: int, db: Session = Depends(private_db)):
    investment = owned_investment(db, investment_id)
    balances = principal_balances(history(db, investment_id))
    lots = db.scalars(select(Lot).where(Lot.investment_id == investment_id, Lot.owner_id == db.info.get("owner_id")).order_by(Lot.application_date, Lot.id))
    return InvestmentDetail(**InvestmentOutput.model_validate(investment).model_dump(),
        principal_balance=total_principal(balances), lots=[LotOutput(id=lot.id,
            application_date=lot.application_date, principal_balance=balances.get(lot.id, Decimal(0))) for lot in lots])


@router.get("/investments/{investment_id}/movements", response_model=list[MovementOutput])
def list_movements(investment_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    return list(db.scalars(select(Movement).where(Movement.investment_id == investment_id,
        Movement.owner_id == db.info.get("owner_id")).order_by(Movement.date, Movement.id).offset(offset).limit(limit)))


@router.get("/investments/{investment_id}/movements/{movement_id}", response_model=MovementOutput)
def movement_detail(investment_id: int, movement_id: int, db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    movement = db.scalar(select(Movement).where(Movement.id == movement_id, Movement.investment_id == investment_id,
        Movement.owner_id == db.info.get("owner_id")))
    if movement is None:
        raise HTTPException(404, "Movimentação não encontrada")
    return movement


@router.post("/investments/{investment_id}/applications", status_code=201, response_model=MovementOutput)
def apply_principal(investment_id: int, data: ApplicationInput, db: Session = Depends(private_db)):
    investment = owned_investment(db, investment_id)
    movements = locked_history(db, investment_id, data.date)
    if not investment.application_date <= data.date <= investment.maturity_date:
        raise HTTPException(422, "Aplicação fora das datas do contrato")
    if not movements and data.date != investment.application_date:
        raise HTTPException(422, "Primeira aplicação deve coincidir com a data de aplicação do contrato")
    lot = Lot(investment_id=investment_id, owner_id=db.info.get("owner_id"), application_date=data.date)
    db.add(lot)
    db.flush()
    movement = Movement(investment_id=investment_id, lot_id=lot.id, owner_id=db.info.get("owner_id"),
        kind="APPLICATION", **data.model_dump())
    db.add(movement)
    db.flush()
    payload = MovementOutput.model_validate(movement)
    db.commit()
    return payload


@router.post("/investments/{investment_id}/redemptions", status_code=201, response_model=MovementOutput)
def redeem_principal(investment_id: int, data: RedemptionInput, db: Session = Depends(private_db)):
    owned_investment(db, investment_id)
    movements = locked_history(db, investment_id, data.date)
    lot = db.scalar(select(Lot).where(Lot.id == data.lot_id, Lot.investment_id == investment_id,
        Lot.owner_id == db.info.get("owner_id")))
    if lot is None:
        raise HTTPException(404, "Lote não encontrado")
    if data.date < lot.application_date or data.principal_amount > principal_balances(movements).get(lot.id, Decimal(0)):
        raise HTTPException(422, "Data inválida ou resgate de principal superior ao saldo do lote")
    movement = Movement(investment_id=investment_id, owner_id=db.info.get("owner_id"), kind="REDEMPTION", **data.model_dump())
    db.add(movement)
    db.flush()
    payload = MovementOutput.model_validate(movement)
    db.commit()
    return payload
