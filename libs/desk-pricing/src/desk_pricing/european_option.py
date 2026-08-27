"""Black-Scholes value for a European call or put using a curve discount factor."""

import math

from desk_pricing.curves import discount_factor


def _normal_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


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
        return (
            max(spot - strike, 0.0)
            if option_type == "CALL"
            else max(strike - spot, 0.0)
        )
    if discount <= 0:
        raise ValueError("discount factor must be positive")
    if volatility <= 0:
        forward_spot = spot / discount
        payoff = (
            max(forward_spot - strike, 0.0)
            if option_type == "CALL"
            else max(strike - forward_spot, 0.0)
        )
        return discount * payoff

    vol_time = volatility * math.sqrt(maturity_years)
    d1 = (
        math.log(spot / strike)
        - math.log(discount)
        + 0.5 * volatility * volatility * maturity_years
    ) / vol_time
    d2 = d1 - vol_time
    if option_type == "CALL":
        return spot * _normal_cdf(d1) - strike * discount * _normal_cdf(d2)
    return strike * discount * _normal_cdf(-d2) - spot * _normal_cdf(-d1)


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
