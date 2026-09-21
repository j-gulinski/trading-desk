from decimal import Decimal

RETURN_PERCENT_STEP = Decimal("0.000001")


def signed_quantity(side, quantity):
    return -quantity if side == "SELL" else quantity


def position_value(price, quantity, multiplier=1):
    return price * quantity * multiplier


def pnl(side, price, entry_price, quantity, multiplier=1):
    return (price - entry_price) * signed_quantity(side, quantity) * multiplier


def notional(price, quantity, multiplier=1):
    return abs(position_value(price, quantity, multiplier))


def record_totals(entry_price, quantity, multiplier, pnl_amount):
    """Entry notional and the return it implies — the denominators a P&L row needs."""
    base = notional(entry_price, quantity, multiplier)
    if not base:
        return {"notional": base, "return_percent": None}
    return {
        "notional": base,
        "return_percent": (pnl_amount / base * 100).quantize(RETURN_PERCENT_STEP),
    }
