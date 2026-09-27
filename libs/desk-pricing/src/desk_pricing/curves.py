"""Curve interpolation, discount factors, implied forward rates and par rates."""

import math

CURVE_CONVENTION = {
    "interpolation": "LINEAR_ZERO_RATE",
    "extrapolation": "FLAT_CLAMP",
    "compounding": "ANNUAL_DISCRETE",
}


def curve_convention():
    return dict(CURVE_CONVENTION)


def rate_at(tenors, rates, t):
    """LINEAR_ZERO_RATE: r(t) = r0 + (r1 - r0) * (t - t0) / (t1 - t0)."""
    if t <= tenors[0]:
        return rates[0]
    if t >= tenors[-1]:
        return rates[-1]
    for index in range(1, len(tenors)):
        if t <= tenors[index]:
            t0, t1 = tenors[index - 1], tenors[index]
            r0, r1 = rates[index - 1], rates[index]
            return r0 + (r1 - r0) * (t - t0) / (t1 - t0)


def discount_factor(curve, t):
    """ANNUAL_DISCRETE: discount(t) = (1 + rate_at(t)) ** -t."""
    if t <= 0:
        return 1.0
    rate = rate_at(curve["tenors"], curve["rates"], t)
    return 1.0 / (1.0 + rate) ** t


def forward_rate(curve, t_start, t_end):
    if t_end <= t_start:
        return 0.0
    return discount_factor(curve, t_start) / discount_factor(curve, t_end) - 1.0


def curve_position(tenors, t):
    """How rate_at reads t: a curve point, between two points, or flat beyond the ends."""
    if t in tenors:
        return {"method": "POINT", "tenors": [t]}
    if t < tenors[0]:
        return {"method": "FLAT_BEFORE", "tenors": [tenors[0]]}
    if t > tenors[-1]:
        return {"method": "FLAT_AFTER", "tenors": [tenors[-1]]}
    right = next(index for index, tenor in enumerate(tenors) if t < tenor)
    return {"method": "INTERPOLATED", "tenors": [tenors[right - 1], tenors[right]]}


def par_rate(curve, maturity, payments_per_year):
    """Fixed rate that makes a fixed leg worth par: (1 - DF(T)) / sum(accrual * DF(t))."""
    periods = max(1, math.ceil(maturity * payments_per_year))
    annuity, previous = 0.0, 0.0
    for period in range(1, periods + 1):
        payment_time = min(period / payments_per_year, maturity)
        annuity += (payment_time - previous) * discount_factor(curve, payment_time)
        previous = payment_time
    return (1.0 - discount_factor(curve, maturity)) / annuity if annuity else None
