"""IRS fixed/floating leg values and directional net present value."""

import math

from desk_pricing.curves import discount_factor, forward_rate


def irs_valuation(meta, curve):
    maturity = float(meta["maturity_years"])
    notional = float(meta["notional"])
    fixed_rate = float(meta["fixed_rate"]) / 100.0
    payments_per_year = int(meta["payments_per_year"])
    if maturity <= 0:
        return 0.0, {"fixed_leg_pv": 0.0, "floating_leg_pv": 0.0, "par_rate": None}
    if notional <= 0 or payments_per_year <= 0:
        raise ValueError("notional and payments_per_year must be positive")

    periods = max(1, int(math.ceil(maturity * payments_per_year)))
    regular_accrual = 1.0 / payments_per_year
    annuity = 0.0
    fixed_leg_pv = 0.0
    floating_leg_pv = 0.0
    previous_payment_time = 0.0
    for period in range(1, periods + 1):
        payment_time = min(period * regular_accrual, maturity)
        period_accrual = payment_time - previous_payment_time
        payment_discount = discount_factor(curve, payment_time)
        annuity += notional * period_accrual * payment_discount
        fixed_cashflow = notional * fixed_rate * period_accrual
        fixed_leg_pv += fixed_cashflow * payment_discount
        floating_cashflow = notional * forward_rate(
            curve, previous_payment_time, payment_time
        )
        floating_leg_pv += floating_cashflow * payment_discount
        previous_payment_time = payment_time
    price = floating_leg_pv - fixed_leg_pv
    if meta["direction"] == "RECEIVE_FIXED_PAY_FLOAT":
        price = -price
    elif meta["direction"] != "PAY_FIXED_RECEIVE_FLOAT":
        raise ValueError("unsupported IRS direction")
    return price, {"fixed_leg_pv": fixed_leg_pv, "floating_leg_pv": floating_leg_pv,
                   "par_rate": floating_leg_pv / annuity * 100 if annuity else None}
