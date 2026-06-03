from decimal import Decimal


def compute_pnl(side, current_price, trade_price, quantity, multiplier=1):
    if side == "SELL":
        unrealized = (trade_price - current_price) * quantity * multiplier
    else:
        unrealized = (current_price - trade_price) * quantity * multiplier
    realized = Decimal("0")
    total = realized + unrealized
    return unrealized, realized, total
