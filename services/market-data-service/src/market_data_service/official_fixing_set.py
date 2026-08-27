from desk_runtime.db import session_scope
from desk_domain.models import Trade
from desk_domain.providers import ECB, NBP
from market_data_service.config import ECB_FIXING_SYMBOLS, NBP_FIXING_SYMBOLS, NBP_GOLD_SYMBOL


def reportable_trade_currencies():
    with session_scope() as session:
        rows = (
            session.query(Trade.trade_currency)
            .filter(Trade.status.in_(("ACTIVE", "CLOSED")))
            .distinct()
            .all()
        )
    return {currency for (currency,) in rows if currency}


def nbp_fixing_symbols(trade_currencies):
    pairs = {f"{code}PLN" for code in trade_currencies - {"PLN"}}
    return frozenset(NBP_FIXING_SYMBOLS) | pairs


def ecb_fixing_symbols(trade_currencies):
    pairs = {f"EUR{code}" for code in trade_currencies - {"EUR"}}
    return frozenset(ECB_FIXING_SYMBOLS) | pairs


def official_fixing_board_symbols():
    currencies = reportable_trade_currencies()
    return {
        NBP: nbp_fixing_symbols(currencies),
        ECB: ecb_fixing_symbols(currencies),
    }


def is_gold(symbol):
    return symbol == NBP_GOLD_SYMBOL
