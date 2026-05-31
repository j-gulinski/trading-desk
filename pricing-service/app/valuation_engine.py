from app import persistence


def calculate_bond_fair_value(face_value, coupon_rate, maturity_years, payments_per_year, yield_rate):
    annual_coupon = face_value * coupon_rate
    total_periods = int(maturity_years * payments_per_year)
    price = 0
    for t in range(1, total_periods + 1):
        cashflow = annual_coupon / payments_per_year
        if t == total_periods:
            cashflow += face_value
        present_value = cashflow / (1 + yield_rate / payments_per_year) ** t
        price += present_value
    return price


def update_pricing(tick):
    instrument_id = tick["instrument_id"]
    asset_type = tick["asset_type"]
    if instrument_id not in persistence.market_state:
        return None

    if asset_type == "EQUITY":
        persistence.market_state[instrument_id]["bid"] = tick["bid"]
        persistence.market_state[instrument_id]["ask"] = tick["ask"]
        persistence.market_state[instrument_id]["last"] = tick["last"]
        persistence.market_state[instrument_id]["fair_value"] = round(
            (tick["bid"] + tick["ask"]) / 2, 4
        )
    elif asset_type == "BOND":
        persistence.market_state[instrument_id]["yield"] = tick["yield"]
        persistence.market_state[instrument_id]["fair_value"] = round(
            calculate_bond_fair_value(
                persistence.market_state[instrument_id]["face_value"],
                persistence.market_state[instrument_id]["coupon_rate"],
                persistence.market_state[instrument_id]["maturity_years"],
                persistence.market_state[instrument_id]["payments_per_year"],
                tick["yield"],
            ),
            4,
        )
    elif asset_type == "FX_FORWARD":
        persistence.market_state[instrument_id]["spot"] = tick["spot"]
        persistence.market_state[instrument_id]["domestic_rate"] = tick["domestic_rate"]
        persistence.market_state[instrument_id]["foreign_rate"] = tick["foreign_rate"]
        persistence.market_state[instrument_id]["fair_value"] = round(
            (
                tick["spot"]
                * (1 + tick["domestic_rate"] * persistence.market_state[instrument_id]["tenor_years"])
                / (1 + tick["foreign_rate"] * persistence.market_state[instrument_id]["tenor_years"])
            ),
            4,
        )
    else:
        return None

    return {
        "instrument_id": persistence.market_state[instrument_id]["instrument_id"],
        "fair_value": persistence.market_state[instrument_id]["fair_value"],
        "currency": persistence.market_state[instrument_id]["currency"],
        "timestamp": tick["timestamp"],
    }
