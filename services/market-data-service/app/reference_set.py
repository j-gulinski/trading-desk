from shared.db import session_scope
from shared.models import Trade
from shared.providers import ECB, NBP
from app.config import ECB_REFERENCE_SYMBOLS, NBP_GOLD_SYMBOL, NBP_REFERENCE_SYMBOLS


def active_trade_currencies():
    with session_scope() as session:
        rows = (
            session.query(Trade.trade_currency)
            .filter(Trade.status == "ACTIVE")
            .distinct()
            .all()
        )
    return {currency for (currency,) in rows if currency}


def nbp_symbols(trade_currencies):
    pairs = {f"{code}PLN" for code in trade_currencies - {"PLN"}}
    return frozenset(NBP_REFERENCE_SYMBOLS) | pairs


def ecb_symbols(trade_currencies):
    pairs = {f"EUR{code}" for code in trade_currencies - {"EUR"}}
    return frozenset(ECB_REFERENCE_SYMBOLS) | pairs


def reference_board_symbols():
    currencies = active_trade_currencies()
    return {NBP: nbp_symbols(currencies), ECB: ecb_symbols(currencies)}


def is_gold(symbol):
    return symbol == NBP_GOLD_SYMBOL
