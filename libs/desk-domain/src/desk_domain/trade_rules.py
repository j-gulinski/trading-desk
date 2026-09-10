from decimal import Decimal

from desk_domain.instruments import FinancialInstrument
from desk_domain.symbols import TRADE_QUANTITY_MAX, TRADE_QUANTITY_MIN


def decimal_value(value, label):
    try:
        number = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        raise ValueError(f"{label} must be a finite number") from None
    if not number.is_finite():
        raise ValueError(f"{label} must be a finite number")
    return number


def validate_position(instrument: FinancialInstrument, side, quantity, price):
    asset_class = instrument.asset_class
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if side not in instrument.allowed_sides:
        raise ValueError(f"{asset_class} side must be {' or '.join(instrument.allowed_sides)}; direction is defined by its terms")
    quantity = decimal_value(quantity, "quantity")
    if not TRADE_QUANTITY_MIN <= quantity <= TRADE_QUANTITY_MAX:
        raise ValueError(f"quantity must be between {TRADE_QUANTITY_MIN} and {TRADE_QUANTITY_MAX}")
    if instrument.whole_quantity and quantity != quantity.to_integral_value():
        raise ValueError(f"{asset_class} quantity must be a whole number")
    if instrument.fixed_quantity is not None and quantity != instrument.fixed_quantity:
        raise ValueError(f"{asset_class} quantity must be {instrument.fixed_quantity}; {instrument.size_term or 'the contract terms'} defines size")
    price = decimal_value(price, "trade_price")
    if not instrument.allows_negative_price and price <= 0:
        raise ValueError("trade_price must be greater than zero")
    return quantity, price
