"""Pure valuation of an existing cost-basis snapshot. No HTTP, DB or realized-P/L changes."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_EVEN
from typing import Literal
from pydantic import BaseModel
from .market_data.types import Quote


class ValuedHolding(BaseModel):
    ticker: str
    quantity: Decimal
    cost: Decimal
    average_price: Decimal
    quote: Quote
    market_value: Decimal | None
    unrealized_profit: Decimal | None
    return_percent: Decimal | None


class ValuationTotals(BaseModel):
    status: Literal["complete", "stale", "partial", "unavailable", "empty"]
    calculated_at: datetime
    is_complete: bool
    unrealized_profit: Decimal | None
    return_percent: Decimal | None
    open_cost: Decimal
    partial_market_value: Decimal
    covered_cost: Decimal
    covered_positions: int
    total_positions: int
    missing_tickers: list[str]
    quoted_at_min: datetime | None
    quoted_at_max: datetime | None


class PortfolioValuation(BaseModel):
    ledger_as_of: datetime
    acquisition_cost: Decimal
    total_purchases: Decimal
    sale_proceeds: Decimal
    realized_profit: Decimal
    market_value: Decimal | None
    holdings: list[ValuedHolding]
    valuation: ValuationTotals


def usable_quote(ticker: str, quote: Quote | None, now: datetime) -> Quote:
    if quote is None:
        return Quote(ticker=ticker, status="unavailable", reason="missing_quote")
    if quote.price is None:
        return quote
    try:
        price = Decimal(quote.price)
        valid = (quote.ticker == ticker and quote.status in ("ok", "stale")
                 and quote.currency == "BRL" and price.is_finite() and price > 0
                 and price <= Decimal("1e12") and price.as_tuple().exponent >= -8
                 and quote.quoted_at is not None and quote.quoted_at.tzinfo is not None
                 and quote.quoted_at <= now + timedelta(seconds=60))
    except (InvalidOperation, ValueError):
        valid = False
    if not valid:
        return quote.model_copy(update={"price": None, "status": "unavailable", "reason": "invalid_quote"})
    age = (now - quote.quoted_at).total_seconds()
    if age > 96 * 3600:
        return quote.model_copy(update={"price": None, "status": "unavailable", "reason": "quote_too_old", "is_stale": True})
    stale = quote.is_stale or quote.status == "stale" or age > 75 * 60
    return quote.model_copy(update={"is_stale": stale, "status": "stale" if stale else "ok"})


def value_portfolio(summary: dict, quotes: list[Quote], *, now: datetime | None = None,
                    ledger_as_of: datetime | None = None) -> PortfolioValuation:
    now = now or datetime.now(timezone.utc)
    counts = Counter(q.ticker for q in quotes)
    by_ticker = {q.ticker: q for q in quotes if counts[q.ticker] == 1}
    positions, missing, timestamps = [], [], []
    with localcontext() as ctx:
        # Product of two Numeric(20,8) values must not be rounded to 28 significant digits.
        # The legacy cost-basis/realized results are reused verbatim, never recomputed here.
        ctx.prec, ctx.rounding = 64, ROUND_HALF_EVEN
        subtotal, covered_cost = Decimal(0), Decimal(0)
        for holding in summary["holdings"]:
            ticker = holding["ticker"]
            quote = usable_quote(ticker, by_ticker.get(ticker), now)
            if counts[ticker] > 1:
                quote = Quote(ticker=ticker, status="unavailable", reason="ambiguous_quote")
            market_value = profit = percent = None
            if quote.price is not None:
                market_value = holding["quantity"] * Decimal(quote.price)
                profit = market_value - holding["cost"]
                percent = profit / holding["cost"] * 100 if holding["cost"] > 0 else None
                subtotal += market_value
                covered_cost += holding["cost"]
                timestamps.append(quote.quoted_at)
            else:
                missing.append(ticker)
            positions.append(ValuedHolding(**holding, quote=quote, market_value=market_value,
                                           unrealized_profit=profit, return_percent=percent))
        complete = not missing
        open_cost = sum((p.cost for p in positions), Decimal(0))
        market_value = subtotal if complete else None
        profit = market_value - open_cost if complete else None
        percent = profit / open_cost * 100 if complete and open_cost > 0 else None
        status = ("empty" if not positions else "unavailable" if len(missing) == len(positions)
                  else "partial" if missing else "stale" if any(p.quote.is_stale for p in positions)
                  else "complete")
        return PortfolioValuation(
            ledger_as_of=ledger_as_of or now,
            **{k: summary[k] for k in ("acquisition_cost", "total_purchases", "sale_proceeds", "realized_profit")},
            market_value=market_value, holdings=positions,
            valuation=ValuationTotals(status=status, calculated_at=now, is_complete=complete,
                unrealized_profit=profit, return_percent=percent, open_cost=open_cost, partial_market_value=subtotal,
                covered_cost=covered_cost, covered_positions=len(positions) - len(missing),
                total_positions=len(positions), missing_tickers=missing,
                quoted_at_min=min(timestamps) if timestamps else None,
                quoted_at_max=max(timestamps) if timestamps else None))
