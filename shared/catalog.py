import os

# The symbol whose ticks drive book alpha/beta sampling. Env-overridable so a real
# index series (e.g. SPY once external market data is wired in) is a config change,
# not a code change.
BENCHMARK_SYMBOL = os.environ.get("BENCHMARK_SYMBOL", "MARKET_INDEX")
DEFAULT_CURVE = "USD_GOV"
DEFAULT_VOLATILITY = 0.22
CURVE_PRICED_ASSET_CLASSES = ("BOND", "IRS", "EUROPEAN_OPTION")

INSTRUMENT_CATALOG = {
    "ACME": {
        "asset_class": "EQUITY",
        "currency": "USD"
    },
    "EURUSD": {
        "asset_class": "FX",
        "currency": "USD",
        "tenor_years": 1.0
    },
    "GOVT_2Y": {
        "asset_class": "BOND",
        "currency": "USD",
        "coupon_rate": 0.04,
        "maturity_years": 2,
        "payments_per_year": 1,
        "face_value": 1000,
        "curve": "USD_GOV",
    },
    "GOVT_5Y": {
        "asset_class": "BOND",
        "currency": "USD",
        "coupon_rate": 0.05,
        "maturity_years": 5,
        "payments_per_year": 1,
        "face_value": 1000,
        "curve": "USD_GOV",
    },
    "XAUUSD": {
        "asset_class": "COMMODITY",
        "currency": "USD"
    },
    "ES_FUT": {
        "asset_class": "FUTURES",
        "currency": "USD",
        "multiplier": 50
    },
}


def public_instrument_catalog():
    return [
        {"symbol": symbol, **dict(terms)}
        for symbol, terms in sorted(INSTRUMENT_CATALOG.items())
    ]
