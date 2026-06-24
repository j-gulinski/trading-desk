def fx_forward(spot, domestic_rate, foreign_rate, tenor_years):
    return spot * (1 + domestic_rate * tenor_years) / (1 + foreign_rate * tenor_years)


def rate_at(tenors, rates, t):
    if t <= tenors[0]:
        return rates[0]
    if t >= tenors[-1]:
        return rates[-1]
    for i in range(1, len(tenors)):
        if t <= tenors[i]:
            t0, t1, r0, r1 = tenors[i - 1], tenors[i], rates[i - 1], rates[i]
            return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
    return rates[-1]


def bond_pv(meta, curve):
    face = meta["face_value"]
    ppy = meta["payments_per_year"]
    periods = int(meta["maturity_years"] * ppy)
    coupon = face * meta["coupon_rate"] / ppy
    pv = 0.0
    for i in range(1, periods + 1):
        t = i / ppy
        r = rate_at(curve["tenors"], curve["rates"], t)
        cashflow = coupon + (face if i == periods else 0.0)
        pv += cashflow / (1 + r) ** t
    return pv
