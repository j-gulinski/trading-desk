import uuid
import logging
import threading

from shared.db import session_scope
from shared.models import Trade, Valuation
from shared.functions import utcnow, get_iso_timestamp

data_lock = threading.Lock()
clients_lock = threading.Lock()

market_data_connection = "DISCONNECTED"
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
                "quantity": float(t.quantity),
                "trade_price": float(t.trade_price),
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
        logging.exception("Failed to persist valuation for trade %s", valuation.get("trade_id"))


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
            qty = float(t.quantity)
            trade_price = float(t.trade_price)
            close_price = float(t.close_price) if t.close_price is not None else trade_price
            multiplier = (t.trade_metadata or {}).get("multiplier", 1)
            if t.side == "SELL":
                realized = (trade_price - close_price) * qty * multiplier
            else:
                realized = (close_price - trade_price) * qty * multiplier
            fair_value = close_price * qty * multiplier

            valuation = {
                "trade_id": str(t.trade_id),
                "book_id": str(t.book_id),
                "asset_class": t.asset_class,
                "symbol": t.symbol,
                "currency": t.trade_currency,
                "fair_value": round(fair_value, 4),
                "market_value": round(fair_value, 4),
                "unrealized_pnl": 0.0,
                "realized_pnl": round(realized, 4),
                "total_pnl": round(realized, 4),
                "valuation_time": get_iso_timestamp(),
                "valuation_payload": {"close_price": close_price, "multiplier": multiplier, "final": True},
            }
            session.add(Valuation(
                valuation_id=uuid.uuid4(),
                trade_id=t.trade_id,
                book_id=t.book_id,
                asset_class=t.asset_class,
                valuation_time=utcnow(),
                fair_value=valuation["fair_value"],
                market_value=valuation["market_value"],
                unrealized_pnl=0,
                realized_pnl=valuation["realized_pnl"],
                total_pnl=valuation["total_pnl"],
                currency=t.trade_currency,
                valuation_payload=valuation["valuation_payload"],
                created_at=utcnow(),
            ))
            t.valuation_finalized = True
            finals.append(valuation)
    return finals
