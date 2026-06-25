import uuid
import threading
from decimal import Decimal

from shared.db import session_scope
from shared.models import Trade, Valuation
from shared.functions import utcnow, get_iso_timestamp
from shared.logging_config import get_logger
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)

data_lock = threading.Lock()
clients_lock = threading.Lock()

ticks_received = 0
last_event_timestamp = None
client_event_queues = set()

# Market state cache
spots = {}
curves = {}

active_trades = {}
latest_valuations = {}


def update_spot(tick):
    with data_lock:
        spots[tick["symbol"]] = tick


def update_curve(tick):
    with data_lock:
        curves[tick["curve_name"]] = tick


def get_spot(symbol):
    with data_lock:
        return spots.get(symbol)


def get_curve(name):
    with data_lock:
        return curves.get(name)


def trades_for_symbol(symbol):
    with data_lock:
        return [t for t in active_trades.values() if t["symbol"] == symbol]


def bond_trades():
    with data_lock:
        return [t for t in active_trades.values() if t["asset_class"] == "BOND"]


def record_valuation(valuation):
    with data_lock:
        latest_valuations[valuation["trade_id"]] = valuation


def all_valuations():
    with data_lock:
        return list(latest_valuations.values())


def get_valuation(trade_id):
    with data_lock:
        return latest_valuations.get(trade_id)


def refresh_active_trades():
    fresh = {}
    with session_scope() as session:
        for t in session.query(Trade).filter(Trade.status == "ACTIVE").all():
            fresh[str(t.trade_id)] = {
                "trade_id": str(t.trade_id),
                "book_id": str(t.book_id),
                "asset_class": t.asset_class,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "trade_price": t.trade_price,
                "currency": t.trade_currency,
                "metadata": t.trade_metadata or {},
            }
    global active_trades
    with data_lock:
        active_trades = fresh
    return len(fresh)


def save_valuation(valuation):
    try:
        with session_scope() as session:
            session.add(Valuation(
                valuation_id=uuid.uuid4(),
                trade_id=uuid.UUID(valuation["trade_id"]),
                book_id=uuid.UUID(valuation["book_id"]),
                asset_class=valuation["asset_class"],
                valuation_time=utcnow(),
                fair_value=valuation["fair_value"],
                market_value=valuation.get("market_value"),
                unrealized_pnl=valuation["unrealized_pnl"],
                realized_pnl=valuation["realized_pnl"],
                total_pnl=valuation["total_pnl"],
                currency=valuation["currency"],
                market_data_reference=valuation.get("market_data_reference"),
                valuation_payload=valuation.get("valuation_payload"),
                created_at=utcnow(),
            ))
    except Exception:
        log.exception("valuation_persist_failed", trade_id=valuation.get("trade_id"))


def finalize_closed_trades():
    """For CLOSED trades not yet finalized: compute realized PnL once, write a final
    valuation (unrealized=0, total=realized), and flip valuation_finalized."""
    finals = []
    with session_scope() as session:
        rows = (
            session.query(Trade)
            .filter(Trade.status == "CLOSED", Trade.valuation_finalized.is_(False))
            .all()
        )
        for t in rows:
            qty = t.quantity
            trade_price = t.trade_price
            multiplier = int((t.trade_metadata or {}).get("multiplier", 1))

            if t.close_price is not None:
                close_price = t.close_price
                if t.side == "SELL":
                    realized = (trade_price - close_price) * qty * multiplier
                else:
                    realized = (close_price - trade_price) * qty * multiplier
                fair_value = close_price * qty * multiplier
                payload = {"close_price": str(close_price), "multiplier": multiplier, "final": True}
            else:
                # close all - (presentation only purpose) no close price, so we mark the trade at market and compute realized PnL from the last valuation
                last = get_valuation(str(t.trade_id))
                if last is not None:
                    realized = Decimal(str(last["unrealized_pnl"]))
                    fair_value = Decimal(str(last["fair_value"]))
                else:
                    realized = Decimal("0")
                    fair_value = trade_price * qty * multiplier
                payload = {"close_price": None, "multiplier": multiplier, "final": True, "marked_at_market": True}

            valuation = {
                "trade_id": str(t.trade_id),
                "book_id": str(t.book_id),
                "asset_class": t.asset_class,
                "symbol": t.symbol,
                "currency": t.trade_currency,
                "fair_value": fair_value,
                "market_value": fair_value,
                "unrealized_pnl": Decimal("0"),
                "realized_pnl": realized,
                "total_pnl": realized,
                "valuation_time": get_iso_timestamp(),
                "valuation_payload": payload,
            }
            session.add(Valuation(
                valuation_id=uuid.uuid4(),
                trade_id=t.trade_id,
                book_id=t.book_id,
                asset_class=t.asset_class,
                valuation_time=utcnow(),
                fair_value=fair_value,
                market_value=fair_value,
                unrealized_pnl=Decimal("0"),
                realized_pnl=realized,
                total_pnl=realized,
                currency=t.trade_currency,
                valuation_payload=valuation["valuation_payload"],
                created_at=utcnow(),
            ))
            t.valuation_finalized = True
            finals.append(valuation)
    return finals
