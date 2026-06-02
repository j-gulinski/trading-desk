def compute_pnl(side, current_price, trade_price, quantity, multiplier=1):
    if side == "SELL":
        unrealized = (trade_price - current_price) * quantity * multiplier
    elif side == "BUY":
        unrealized = (current_price - trade_price) * quantity * multiplier
    realized = 0.0
    total = realized + unrealized
    return unrealized, realized, total
