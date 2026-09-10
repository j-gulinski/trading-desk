def signed_quantity(side, quantity):
    return -quantity if side == "SELL" else quantity


def position_value(price, quantity, multiplier=1):
    return price * quantity * multiplier


def pnl(side, price, entry_price, quantity, multiplier=1):
    return (price - entry_price) * signed_quantity(side, quantity) * multiplier
