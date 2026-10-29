"""Private portfolio flows and current composition, using recorded data only."""
from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .access import private_db
from .auth import authenticate
from .fixed_income.models import Investment, InvestmentArchive, Lot
from .fixed_income.observations import PositionObservation
from .fixed_income.projection import effective_movements
from .models import Operation

router = APIRouter(prefix="/api/dashboard", tags=["portfolio"])
ZERO = Decimal("0")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _money(value: Decimal) -> str:
    return str(value)


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def aggregate_capital_flows(operations, movements, *, start: date, end: date):
    """Recorded cash movements and principal flows; never market value or return."""
    by_day = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO])  # equity purchases, CDB applications, principal redemptions, net equity sales
    all_dates = []
    with localcontext() as ctx:
        ctx.prec = 64
        for op in operations:
            amount = op.quantity * op.price
            if op.kind == "BUY":
                amount += op.fees
                by_day[op.date][0] += amount
            else:
                amount -= op.fees
                by_day[op.date][3] += amount
            all_dates.append(op.date)
        for movement in movements:
            amount = movement.principal_amount
            if movement.kind == "APPLICATION":
                by_day[movement.date][1] += amount
            elif movement.kind == "REDEMPTION":
                by_day[movement.date][2] += amount
            all_dates.append(movement.date)

        cumulative_in = cumulative_out = ZERO
        points = []
        for day in sorted(by_day):
            if day > end:
                continue
            equity_purchases, applications, redemptions, sales = by_day[day]
            contributions = equity_purchases + applications
            if day < start:
                cumulative_in += contributions
                cumulative_out += redemptions + sales
                continue
            if not points and start != date.min and day > start:
                points.append({"date": start.isoformat(), "contributions": _money(ZERO),
                    "redemptions": _money(ZERO), "sales": _money(ZERO),
                    "cumulative_contributions": _money(cumulative_in),
                    "cumulative_withdrawals": _money(cumulative_out),
                    "net_accumulated": _money(cumulative_in - cumulative_out)})
            cumulative_in += contributions
            cumulative_out += redemptions + sales
            if start <= day <= end:
                points.append({"date": day.isoformat(), "contributions": _money(contributions),
                    "redemptions": _money(redemptions), "sales": _money(sales), "net_accumulated": _money(cumulative_in - cumulative_out)})
                points[-1]["cumulative_contributions"] = _money(cumulative_in)
                points[-1]["cumulative_withdrawals"] = _money(cumulative_out)
        observed = [day for day in all_dates if day <= end]
        coverage_start = min(observed).isoformat() if observed else None
        coverage_end = max(observed).isoformat() if observed else None
        visible = [day for day in observed if day >= start]
        if start != date.min and not points and observed:
            points.append({"date": start.isoformat(), "contributions": _money(ZERO), "redemptions": _money(ZERO), "sales": _money(ZERO),
                "cumulative_contributions": _money(cumulative_in), "cumulative_withdrawals": _money(cumulative_out),
                "net_accumulated": _money(cumulative_in - cumulative_out)})
        period_equity_purchases = sum((values[0] for day, values in by_day.items() if start <= day <= end), ZERO)
        period_applications = sum((values[1] for day, values in by_day.items() if start <= day <= end), ZERO)
        period_redemptions = sum((values[2] for day, values in by_day.items() if start <= day <= end), ZERO)
        period_sales = sum((values[3] for day, values in by_day.items() if start <= day <= end), ZERO)
        return {"period_start": start.isoformat(), "period_end": end.isoformat(),
            "coverage_start": coverage_start, "coverage_end": coverage_end,
            "coverage": "available" if points and coverage_start and (start == date.min or date.fromisoformat(coverage_start) <= start) else "partial" if points else "unavailable",
            "points": points, "gross_contributions": _money(period_equity_purchases + period_applications),
            "equity_purchases": _money(period_equity_purchases), "cdb_applications": _money(period_applications),
            "redemptions": _money(period_redemptions), "cdb_redemptions": _money(period_redemptions),
            "sales": _money(period_sales), "equity_sale_proceeds": _money(period_sales),
            "cumulative_contributions": _money(cumulative_in),
            "cumulative_withdrawals": _money(cumulative_out),
            "withdrawals": _money(cumulative_out),
            "net_accumulated": _money(cumulative_in - cumulative_out),
            "visible_events": len(visible), "market_value": None, "return": None}


def aggregate_composition(operations, effective, investments, lots, observations, *, as_of: date):
    """Open equity cost and fixed-income principal/declarations with explicit coverage."""
    from .finance import summarize
    holdings = summarize(operations)["holdings"]
    equities = [{"asset": h["ticker"], "value": _money(h["cost"]), "basis": "open_acquisition_cost"} for h in holdings]
    movement_by_investment = defaultdict(list)
    for row in effective:
        movement_by_investment[row.investment_id].append(row)
    lots_by_investment = defaultdict(list)
    for lot in lots:
        lots_by_investment[lot.investment_id].append(lot)
    observations_by_investment = defaultdict(list)
    for obs in observations:
        observations_by_investment[obs.investment_id].append(obs)
    fixed, declared, missing = [], [], []
    with localcontext() as ctx:
        ctx.prec = 64
        for investment in investments:
            asset = investment.product_name
            inv_lots = lots_by_investment[investment.id]
            if inv_lots:
                balance = ZERO
                rows = sorted(movement_by_investment[investment.id], key=lambda m: (m.date, m.id))
                lot_balance = defaultdict(lambda: ZERO)
                for movement in rows:
                    if movement.date <= as_of:
                        delta = movement.principal_amount if movement.kind == "APPLICATION" else -movement.principal_amount
                        lot_balance[movement.lot_id] += delta
                balance = sum(lot_balance.values(), ZERO)
                fixed.append({"asset": asset, "value": _money(balance), "basis": "effective_open_principal"})
            else:
                eligible = [o for o in observations_by_investment[investment.id] if o.as_of <= as_of]
                if eligible:
                    obs = max(eligible, key=lambda o: (o.as_of, o.id))
                    declared.append({"asset": asset, "value": _money(obs.net_value), "as_of": obs.as_of.isoformat(), "basis": "declared_observation"})
                else:
                    missing.append(asset)
    with localcontext() as ctx:
        ctx.prec = 64
        class_totals = {
            "equities_open_cost": _money(sum((h["cost"] for h in holdings), ZERO)),
            "fixed_income_open_principal": _money(sum((Decimal(item["value"]) for item in fixed), ZERO)),
            "declared_positions": _money(sum((Decimal(item["value"]) for item in declared), ZERO)),
        }
    return {"as_of": as_of.isoformat(), "equities": equities, "fixed_income": fixed,
        "declared_positions": declared, "missing_fixed_income": missing,
        "class_totals": class_totals,
        "market_values": None, "coverage": "partial" if missing or equities else "available",
        "missing_components": (["cotações de mercado para ações"] if equities else []) + (["posições sem lote nem observação"] if missing else []),
        "equity_basis": "open_acquisition_cost", "fixed_income_basis": "effective_open_principal",
        "declared_values_separate": True}


@router.get("/capital-flows", dependencies=[Depends(authenticate)])
def capital_flows(period: str = Query("Tudo", pattern="^(1M|3M|6M|1A|Tudo)$"), db: Session = Depends(private_db)):
    today = local_today()
    months = {"1M": 1, "3M": 3, "6M": 6, "1A": 12}.get(period)
    start = _subtract_months(today, months) if months else date.min
    owner = db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(Operation.owner_id == owner, Operation.date <= today).order_by(Operation.date, Operation.id)))
    projected = effective_movements(db)
    movements = list(db.execute(select(projected).where(projected.c.owner_id == owner,
        projected.c.date <= today).order_by(projected.c.date, projected.c.id)).mappings())
    return aggregate_capital_flows(operations, movements, start=start, end=today)


@router.get("/composition", dependencies=[Depends(authenticate)])
def portfolio_composition(db: Session = Depends(private_db)):
    today, owner = local_today(), db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(Operation.owner_id == owner, Operation.date <= today).order_by(Operation.date, Operation.id)))
    projected = effective_movements(db)
    movements = list(db.execute(select(projected).where(projected.c.owner_id == owner, projected.c.date <= today)).mappings())
    investments = list(db.scalars(select(Investment).where(Investment.owner_id == owner,
        ~exists(select(InvestmentArchive.id).where(InvestmentArchive.investment_id == Investment.id)))))
    lots = list(db.scalars(select(Lot).where(Lot.owner_id == owner)))
    observations = list(db.scalars(select(PositionObservation).where(PositionObservation.owner_id == owner,
        PositionObservation.as_of <= today)))
    return aggregate_composition(operations, movements, investments, lots, observations, as_of=today)


@router.get("/movements", dependencies=[Depends(authenticate)])
def unified_movements(db: Session = Depends(private_db)):
    """Chronological view of recorded equity trades and effective CDB ledger rows."""
    owner = db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(Operation.owner_id == owner).order_by(Operation.date, Operation.id)))
    projected = effective_movements(db)
    rows = db.execute(
        select(projected, Investment.product_name)
        .join(Investment, (Investment.id == projected.c.investment_id) & (Investment.owner_id == owner))
        .where(projected.c.owner_id == owner)
        .order_by(projected.c.date, projected.c.id)
    ).all()
    with localcontext() as ctx:
        ctx.prec = 64
        result = [{
            "id": f"equity:{op.id}", "date": op.date.isoformat(), "investment_class": "AÇÕES",
            "asset": op.ticker, "operation": op.kind, "quantity": str(op.quantity),
            "unit_price": str(op.price), "financial_value": str(op.quantity * op.price),
            "fees": str(op.fees), "cash_received": None,
        } for op in operations]
    result.extend({
        "id": f"cdb:{row.id}", "date": row.date.isoformat(), "investment_class": "CDB",
        "asset": row.product_name, "operation": row.kind, "quantity": None,
        "unit_price": None, "financial_value": str(row.principal_amount),
        "fees": None, "cash_received": str(row.cash_received) if row.cash_received is not None else None,
    } for row in rows)
    return sorted(result, key=lambda item: (item["date"], item["id"]))
