"""IRS fixed/floating leg values and directional net present value."""

import math

from desk_pricing.curves import discount_factor, forward_rate


def irs_legs(meta, discount_curve, projection_curve=None):
    projection_curve = projection_curve or discount_curve
    maturity = float(meta["maturity_years"])
    notional = float(meta["notional"])
    fixed_rate = float(meta["fixed_rate"]) / 100.0
    payments_per_year = int(meta["payments_per_year"])
    if maturity <= 0:
        return {"fixed_leg_pv": 0.0, "floating_leg_pv": 0.0}
    if notional <= 0 or payments_per_year <= 0:
        raise ValueError("notional and payments_per_year must be positive")

    periods = max(1, int(math.ceil(maturity * payments_per_year)))
    regular_accrual = 1.0 / payments_per_year
    fixed_leg_pv = 0.0
    floating_leg_pv = 0.0
    previous_payment_time = 0.0
    for period in range(1, periods + 1):
        payment_time = min(period * regular_accrual, maturity)
        period_accrual = payment_time - previous_payment_time
        payment_discount = discount_factor(discount_curve, payment_time)
        fixed_cashflow = notional * fixed_rate * period_accrual
        fixed_leg_pv += fixed_cashflow * payment_discount
        floating_cashflow = notional * forward_rate(
            projection_curve, previous_payment_time, payment_time
        )
        floating_leg_pv += floating_cashflow * payment_discount
        previous_payment_time = payment_time
    return {"fixed_leg_pv": fixed_leg_pv, "floating_leg_pv": floating_leg_pv}


def irs_pv(meta, discount_curve, projection_curve=None):
    legs = irs_legs(meta, discount_curve, projection_curve)
    if meta["direction"] == "PAY_FIXED_RECEIVE_FLOAT":
        return legs["floating_leg_pv"] - legs["fixed_leg_pv"]
    if meta["direction"] == "RECEIVE_FIXED_PAY_FLOAT":
        return legs["fixed_leg_pv"] - legs["floating_leg_pv"]
    raise ValueError("unsupported IRS direction")


def irs_fair_fixed_rate(meta, discount_curve, projection_curve=None):
    """Percent fixed rate that makes the fixed and floating legs equal in PV."""
    unit_fixed_terms = {**meta, "fixed_rate": 100.0}
    legs = irs_legs(unit_fixed_terms, discount_curve, projection_curve)
    unit_fixed_leg = legs["fixed_leg_pv"]
    if unit_fixed_leg == 0:
        return None
    return legs["floating_leg_pv"] / unit_fixed_leg * 100.0
