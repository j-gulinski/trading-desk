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