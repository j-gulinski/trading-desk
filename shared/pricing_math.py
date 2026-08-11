import math


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


def discount_factor(curve, t):
    if t <= 0:
        return 1.0
    rate = rate_at(curve["tenors"], curve["rates"], t)
    return 1.0 / (1.0 + rate) ** t


def normal_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(spot, strike, maturity_years, discount, volatility, option_type):
    spot = float(spot)
    strike = float(strike)
    maturity_years = float(maturity_years)
    discount = float(discount)
    volatility = float(volatility)
    option_type = str(option_type).upper()

    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if option_type not in ("CALL", "PUT"):
        raise ValueError("option_type must be CALL or PUT")
    if maturity_years <= 0:
        return max(spot - strike, 0.0) if option_type == "CALL" else max(strike - spot, 0.0)
    if discount <= 0:
        raise ValueError("discount factor must be positive")
    if volatility <= 0:
        forward_spot = spot / discount
        discounted_payoff = discount * (
            max(forward_spot - strike, 0.0)
            if option_type == "CALL"
            else max(strike - forward_spot, 0.0)
        )
        return discounted_payoff

    vol_time = volatility * math.sqrt(maturity_years)
    d1 = (
        math.log(spot / strike)
        - math.log(discount)
        + 0.5 * volatility * volatility * maturity_years
    ) / vol_time
    d2 = d1 - vol_time
    if option_type == "CALL":
        return spot * normal_cdf(d1) - strike * discount * normal_cdf(d2)
    return strike * discount * normal_cdf(-d2) - spot * normal_cdf(-d1)


def european_option_pv(meta, spot, curve, volatility):
    maturity = float(meta["maturity_years"])
    return black_scholes_price(
        spot=spot,
        strike=meta["strike"],
        maturity_years=maturity,
        discount=discount_factor(curve, maturity),
        volatility=volatility,
        option_type=meta["option_type"],
    )


def forward_rate(curve, t_start, t_end):
    if t_end <= t_start:
        return 0.0
    return discount_factor(curve, t_start) / discount_factor(curve, t_end) - 1.0


def irs_legs(meta, curve, projection_curve=None):
    if projection_curve is None:
        projection_curve = curve
    maturity = float(meta["maturity_years"])
    notional = float(meta["notional"])
    fixed_rate = float(meta["fixed_rate"])
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
        payment_discount = discount_factor(curve, payment_time)
        fixed_cashflow = notional * fixed_rate * period_accrual
        fixed_leg_pv += fixed_cashflow * payment_discount
        floating_cashflow = notional * forward_rate(
            projection_curve, previous_payment_time, payment_time
        )
        floating_leg_pv += floating_cashflow * payment_discount
        previous_payment_time = payment_time
    return {"fixed_leg_pv": fixed_leg_pv, "floating_leg_pv": floating_leg_pv}


def irs_pv(meta, curve, projection_curve=None):
    legs = irs_legs(meta, curve, projection_curve)
    direction = meta["direction"]
    if direction == "PAY_FIXED_RECEIVE_FLOAT":
        return legs["floating_leg_pv"] - legs["fixed_leg_pv"]
    if direction == "RECEIVE_FIXED_PAY_FLOAT":
        return legs["fixed_leg_pv"] - legs["floating_leg_pv"]
    raise ValueError("unsupported IRS direction")



def bond_pv(meta, curve):
    face = meta["face_value"]
    ppy = meta["payments_per_year"]
    periods = int(meta["maturity_years"] * ppy)
    coupon = face * meta["coupon_rate"] / ppy
    pv = 0.0
    for i in range(1, periods + 1):
        t = i / ppy
        cashflow = coupon + (face if i == periods else 0.0)
        pv += cashflow * discount_factor(curve, t)
    return pv

MINIMUM_OBSERVATIONS = 20


def alpha_beta(book_returns, benchmark_returns, minimum_observations=MINIMUM_OBSERVATIONS):
    """OLS regression of book returns on benchmark returns: book = alpha + beta * benchmark.

    With a single regressor the OLS slope reduces to cov/var, so:

        beta      = cov(book, benchmark) / var(benchmark)
        alpha     = mean(book) - beta * mean(benchmark)
        r_squared = cov^2 / (var(book) * var(benchmark))

    Both inputs must be aligned return series sampled over the same periods; the
    estimator does not care what the period is (per tick, per poll, per daily close),
    so alpha is *per observation period* — annualize it at the call site if needed.
    A return here is a fraction (0.01 = 1%), for the book defined against whatever
    capital base the caller divided PnL by; beta scales inversely with that base.

    Returns alpha/beta/r_squared with status READY, or all-None with a guard status:
    INSUFFICIENT_DATA below minimum_observations pairs, ZERO_BENCHMARK_VARIANCE when
    the benchmark has not moved (the slope would divide by zero). r_squared is None
    when the book has not moved (0/0); beta is well-defined there (zero).
    """
    if len(book_returns) != len(benchmark_returns):
        raise ValueError("book and benchmark returns must be aligned")
    empty = {"alpha": None, "beta": None, "r_squared": None}
    observations = len(book_returns)
    if observations < minimum_observations:
        return {**empty, "status": "INSUFFICIENT_DATA"}
    mean_book = sum(book_returns) / observations
    mean_benchmark = sum(benchmark_returns) / observations
    benchmark_variance = (
        sum((value - mean_benchmark) ** 2 for value in benchmark_returns) / observations
    )
    if benchmark_variance == 0:
        return {**empty, "status": "ZERO_BENCHMARK_VARIANCE"}
    book_variance = sum((value - mean_book) ** 2 for value in book_returns) / observations
    covariance = sum(
        (book_value - mean_book) * (benchmark_value - mean_benchmark)
        for book_value, benchmark_value in zip(book_returns, benchmark_returns)
    ) / observations
    beta = covariance / benchmark_variance
    return {
        "alpha": mean_book - beta * mean_benchmark,
        "beta": beta,
        "r_squared": (
            covariance * covariance / (book_variance * benchmark_variance)
            if book_variance > 0
            else None
        ),
        "status": "READY",
    }
