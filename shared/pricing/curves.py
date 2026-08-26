"""Curve interpolation, discount factors and implied forward rates."""


def rate_at(tenors, rates, t):
    if t <= tenors[0]:
        return rates[0]
    if t >= tenors[-1]:
        return rates[-1]
    for index in range(1, len(tenors)):
        if t <= tenors[index]:
            t0, t1 = tenors[index - 1], tenors[index]
            r0, r1 = rates[index - 1], rates[index]
            return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
    return rates[-1]


def discount_factor(curve, t):
    if t <= 0:
        return 1.0
    rate = rate_at(curve["tenors"], curve["rates"], t)
    return 1.0 / (1.0 + rate) ** t


def forward_rate(curve, t_start, t_end):
    if t_end <= t_start:
        return 0.0
    return discount_factor(curve, t_start) / discount_factor(curve, t_end) - 1.0
