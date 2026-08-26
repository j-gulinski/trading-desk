"""Present value of a fixed-coupon bond's coupons and principal."""

import math

from shared.pricing.curves import discount_factor


def bond_pv(meta, curve):
    face = float(meta["face_value"])
    maturity = float(meta["maturity_years"])
    payments_per_year = int(meta["payments_per_year"])
    if face <= 0 or maturity <= 0 or payments_per_year <= 0:
        raise ValueError("face_value, maturity_years and payments_per_year must be positive")
    annual_coupon_rate = float(meta["coupon_rate"]) / 100.0
    periods = max(1, int(math.ceil(maturity * payments_per_year)))
    present_value = 0.0
    previous_payment_time = 0.0
    for period in range(1, periods + 1):
        payment_time = min(period / payments_per_year, maturity)
        accrual = payment_time - previous_payment_time
        coupon = face * annual_coupon_rate * accrual
        cashflow = coupon + (face if period == periods else 0.0)
        present_value += cashflow * discount_factor(curve, payment_time)
        previous_payment_time = payment_time
    return present_value
