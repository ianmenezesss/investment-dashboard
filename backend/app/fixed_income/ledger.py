from decimal import Decimal, localcontext, ROUND_HALF_EVEN


def principal_balances(movements):
    """Principal only. Cash received is never used to infer amortization or income."""
    balances = {}
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 64, ROUND_HALF_EVEN
        for movement in sorted(movements, key=lambda m: (m.date, m.id or 0)):
            balance = balances.get(movement.lot_id, Decimal(0))
            balance += movement.principal_amount if movement.kind == "APPLICATION" else -movement.principal_amount
            if balance < 0:
                raise ValueError("Resgate de principal superior ao saldo do lote")
            balances[movement.lot_id] = balance
    return balances


def total_principal(balances):
    with localcontext() as ctx:
        ctx.prec = 64
        return sum(balances.values(), Decimal(0))
