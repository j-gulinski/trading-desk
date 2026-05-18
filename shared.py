import datetime

INSTRUMENTS = {
    "EQ_ACME": {
        "type": "EQUITY",
        "market_symbol": "ACME",
        "currency": "USD"
    },
    "BOND_GOVT_5Y": {
        "type": "BOND",
        "market_symbol": "GOVT_5Y",
        "currency": "USD",
        "face_value": 1000,
        "coupon_rate": 0.05,
        "maturity_years": 5,
        "payments_per_year": 1
    },
    "FX_EURUSD_1Y": {
        "type": "FX_FORWARD",
        "market_symbol": "EURUSD",
        "currency": "USD",
        "tenor_years": 1.0
    }
}

def get_iso_timestamp():
    return datetime.datetime.utcnow().isoformat()[:-3] + "Z"