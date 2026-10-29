"""Owner-scoped historical mark-to-market for recorded equity operations."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .access import private_db
from .auth import authenticate
from .market_data.brapi import valid_ticker
from .market_data.equity_history import EquityHistoryService, TickerHistory
from .models import Operation
from .portfolio import _subtract_months, local_today

router = APIRouter(prefix="/api/dashboard", tags=["portfolio history"])
ZERO = Decimal("0")


@dataclass(frozen=True)
class HistoricalOperation:
    """Immutable operation data retained after the owner-scoped DB transaction ends."""
    id: int
    ticker: str
    kind: str
    date: date
    quantity: Decimal
    price: Decimal
    fees: Decimal


def aggregate_equity_history(operations, histories: dict[str, TickerHistory], *, start: date, end: date):
    """Rebuild shares chronologically and multiply only by rawClose from that day.

    Operations on a date and split factors effective that date are reflected in
    that session's close. Cash dividends, fees-as-return, cash balances, taxes,
    and unrecorded opening positions are not modeled.
    """
    operations = sorted((op for op in operations if op.date <= end), key=lambda op: (op.date, op.id))
    if not operations:
        return {"period_start": start.isoformat(), "period_end": end.isoformat(), "coverage_start": None,
                "coverage_end": None, "coverage": "empty", "source": "brapi", "price_basis": "raw_close",
                "convention": "Operações e ações societárias da data são refletidas no fechamento do mesmo pregão.",
                "points": [], "missing_tickers": [], "provider_errors": {}}

    first_operation = min(op.date for op in operations)
    operation_days = defaultdict(list)
    action_days = defaultdict(list)
    price_days = defaultdict(dict)
    tickers = sorted({op.ticker for op in operations})
    for op in operations:
        operation_days[op.date].append(op)
    provider_errors = {}
    for ticker in tickers:
        history = histories.get(ticker)
        if history is None:
            provider_errors[ticker] = "history_unavailable"
            continue
        if history.error:
            provider_errors[ticker] = history.error
        for action in history.share_events:
            action_days[action.day].append((ticker, action.factor))
        for bar in history.prices:
            if start <= bar.day <= end:
                price_days[bar.day][ticker] = bar.raw_close

    shares = defaultdict(lambda: ZERO)
    net_invested = ZERO
    points = []
    missing_any = set()
    timeline = sorted(set(operation_days) | set(action_days) | set(price_days))
    with localcontext() as ctx:
        ctx.prec = 64
        for day in timeline:
            if day > end:
                continue
            # Share events take effect on ex-date, before trades made at that
            # session's post-event price and share basis.
            for ticker, factor in action_days[day]:
                shares[ticker] *= factor
            for op in operation_days[day]:
                signed_quantity = op.quantity if op.kind == "BUY" else -op.quantity
                shares[op.ticker] += signed_quantity
                net_invested += op.quantity * op.price + op.fees if op.kind == "BUY" else -(op.quantity * op.price - op.fees)

            if day not in price_days or day < max(start, first_operation):
                continue
            partial_value = ZERO
            held_count = 0
            missing = []
            details = []
            for ticker in tickers:
                quantity = shares[ticker]
                if quantity <= ZERO:
                    continue
                held_count += 1
                price = price_days[day].get(ticker)
                history = histories.get(ticker)
                if price is None or (history and history.error):
                    missing.append(ticker)
                    missing_any.add(ticker)
                    details.append({"ticker": ticker, "quantity": str(quantity), "price": None, "market_value": None})
                    continue
                value = quantity * price
                partial_value += value
                details.append({"ticker": ticker, "quantity": str(quantity), "price": str(price), "market_value": str(value)})
            complete = not missing
            market_value = partial_value if complete else None
            points.append({"date": day.isoformat(), "market_value": str(market_value) if market_value is not None else None,
                "partial_market_value": str(partial_value), "net_invested": str(net_invested),
                "difference_over_net_flows": str(market_value - net_invested) if market_value is not None else None,
                "coverage": "complete" if complete else "partial", "missing_tickers": missing, "holdings": details,
                "held_positions": held_count})

    coverage_start = points[0]["date"] if points else None
    coverage_end = points[-1]["date"] if points else None
    # The first operation is the limit of this ledger: we cannot describe earlier
    # holdings from a trade history that did not yet exist in the application.
    has_partial = bool(missing_any) or first_operation > start
    coverage = "unavailable" if not points else "partial" if has_partial or any(p["coverage"] != "complete" for p in points) else "complete"
    return {"period_start": start.isoformat(), "period_end": end.isoformat(), "coverage_start": coverage_start,
            "coverage_end": coverage_end, "coverage": coverage, "source": "brapi", "price_basis": "raw_close",
            "convention": "Operações e ações societárias da data são refletidas no fechamento do mesmo pregão.",
            "points": points, "missing_tickers": sorted(missing_any), "provider_errors": provider_errors}


def equity_history_service(request: Request) -> EquityHistoryService:
    service = getattr(request.app.state, "equity_history_service", None)
    if service is None:
        raise HTTPException(503, "Serviço de histórico de ações indisponível")
    return service


@router.get("/equity-history", dependencies=[Depends(authenticate)])
async def equity_history(period: str = Query("Tudo", pattern="^(1M|3M|6M|1A|Tudo)$"),
                        db: Session = Depends(private_db), service: EquityHistoryService = Depends(equity_history_service)):
    today = local_today()
    months = {"1M": 1, "3M": 3, "6M": 6, "1A": 12}.get(period)
    rows = list(db.scalars(select(Operation).where(
        Operation.owner_id == db.info.get("owner_id"), Operation.date <= today
    ).order_by(Operation.date, Operation.id)))
    # Rollback below is required before provider I/O. Snapshot only the fields used
    # by the aggregation first: rollback expires ORM instances and clears transaction-
    # local RLS identity, so refreshing those instances afterward hides their rows.
    operations = [HistoricalOperation(
        id=row.id, ticker=row.ticker, kind=row.kind, date=row.date,
        quantity=row.quantity, price=row.price, fees=row.fees,
    ) for row in rows]
    if not operations:
        return aggregate_equity_history([], {}, start=_subtract_months(today, months) if months else today, end=today)

    first_operation = min(op.date for op in operations)
    start = _subtract_months(today, months) if months else first_operation
    price_start = max(start, first_operation)
    tickers = sorted({op.ticker for op in operations})
    db.rollback()  # Release the owner-scoped DB transaction before external HTTP.
    if any(not valid_ticker(ticker) for ticker in tickers):
        # Do not pass stored arbitrary strings to an external URL or query.
        valid_tickers = [ticker for ticker in tickers if valid_ticker(ticker)]
        histories = await service.get(valid_tickers, price_start=price_start, event_start=first_operation, end=today) if valid_tickers else {}
        for ticker in tickers:
            if ticker not in histories:
                histories[ticker] = TickerHistory(error="invalid_ticker")
    else:
        histories = await service.get(tickers, price_start=price_start, event_start=first_operation, end=today)
    return aggregate_equity_history(operations, histories, start=start, end=today)
