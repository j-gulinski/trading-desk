"""European call/put: Black–Scholes and intrinsic payoff."""

import math

from desk_pricing.curves import discount_factor


def _normal_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def intrinsic_payoff(spot, strike, option_type):
    spot = float(spot)
    strike = float(strike)
    option_type = str(option_type).upper()
    if option_type == "CALL":
        return max(spot - strike, 0.0)
    if option_type == "PUT":
        return max(strike - spot, 0.0)
    raise ValueError("option_type must be CALL or PUT")


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
        return intrinsic_payoff(spot, strike, option_type)
    if discount <= 0:
        raise ValueError("discount factor must be positive")
    if volatility <= 0:
        forward_spot = spot / discount
        return discount * intrinsic_payoff(forward_spot, strike, option_type)

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


def black_scholes(terms, spot, curve):
    maturity = float(terms["maturity_years"])
    return {
        "price": black_scholes_price(
            spot, terms["strike"], maturity,
            discount_factor(curve, maturity),
            terms.get("volatility", 0.22),
            terms["option_type"],
        )
    }


def intrinsic(terms, spot, curve=None):
    return {"price": intrinsic_payoff(spot, terms["strike"], terms["option_type"])}
