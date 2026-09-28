import hashlib

SYMBOL_COUNT = 10_000
HELD_COUNT = 1_000
MARKET = "NASDAQ"
CURRENCY = "USD"

SYMBOLS = [f"D{i:05d}" for i in range(1, SYMBOL_COUNT + 1)]
HELD_SYMBOLS = SYMBOLS[:HELD_COUNT]

EQUITY_BOOKS = [f"Equities {i}" for i in range(1, 6)]
TRANSFER_BOOKS = ("Transfer A", "Transfer B")
BOND_BOOK = "Bonds"
IRS_BOOK = "Rates"
OPTION_BOOK = "Options"

BOND_CURVE = "EUR_GOVERNMENT_BONDS_AAA"
IRS_CURVE = "EUR_RISK_FREE"
OPTION_CURVE = "USD_RISK_FREE"


def stable_hash(text):
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8])


def initial_price(sym):
    return round(20 + stable_hash(sym) % 48_001 / 100, 2)


def company_name(sym):
    return f"{sym} Holdings"
