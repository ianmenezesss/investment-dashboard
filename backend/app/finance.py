"""Livro por custo médio. Valores Decimal; sem inferir cotações de mercado."""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext


def summarize(operations):
    with localcontext() as context:
        # NUMERIC(20,8) quantity × price can produce 40 significant digits.
        # Keep those digits through cost allocation without changing global Decimal settings.
        context.prec, context.rounding = 64, ROUND_HALF_EVEN
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
                # A full exit must remove the exact remaining basis; dividing by
                # quantity first can leave a rounding residue for repeating averages.
                removed = (item["cost"] if op.quantity == item["quantity"]
                           else item["cost"] / item["quantity"] * op.quantity)
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
