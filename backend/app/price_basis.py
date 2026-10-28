"""Fee-free weighted purchase basis, separate from the financial cost ledger."""
from decimal import Decimal, localcontext, ROUND_HALF_EVEN


def purchase_price_basis(operations):
    positions = {}
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 64, ROUND_HALF_EVEN
        for op in sorted(operations, key=lambda o: (o.date, o.id or 0)):
            item = positions.setdefault(op.ticker, {"quantity": Decimal(0), "cost": Decimal(0)})
            if op.kind == "BUY":
                item["cost"] += op.quantity * op.price
                item["quantity"] += op.quantity
            else:
                if op.quantity > item["quantity"]:
                    raise ValueError("Venda superior à posição disponível")
                if op.quantity == item["quantity"]:
                    item["cost"] = Decimal(0)
                else:
                    item["cost"] -= item["cost"] / item["quantity"] * op.quantity
                item["quantity"] -= op.quantity
    return positions
