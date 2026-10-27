"""Livro por custo médio. Valores Decimal; sem inferir cotações de mercado."""
from decimal import Decimal


def summarize(operations):
    holdings = {}
    purchases = Decimal(0)
    proceeds = Decimal(0)
    realized = Decimal(0)
    for op in sorted(operations, key=lambda o: (o.date, o.id or 0)):
        item = holdings.setdefault(op.ticker, {"ticker": op.ticker, "quantity": Decimal(0), "cost": Decimal(0)})
        if op.kind == "BUY":
            cost = op.quantity * op.price + op.fees
            item["cost"] += cost
            item["quantity"] += op.quantity
            purchases += cost
        else:
            if op.quantity > item["quantity"]:
                raise ValueError(f"Venda de {op.ticker} excede a posição disponível na data.")
            removed = item["cost"] / item["quantity"] * op.quantity
            net = op.quantity * op.price - op.fees
            realized += net - removed
            proceeds += net
            item["cost"] -= removed
            item["quantity"] -= op.quantity
    return {
        "acquisition_cost": sum((h["cost"] for h in holdings.values()), Decimal(0)),
        "total_purchases": purchases,
        "sale_proceeds": proceeds,
        "realized_profit": realized,
        "market_value": None,
        "holdings": [dict(h, average_price=h["cost"] / h["quantity"]) for h in holdings.values() if h["quantity"]],
    }
