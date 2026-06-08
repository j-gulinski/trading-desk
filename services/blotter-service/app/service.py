import logging
from decimal import Decimal

from app import cache, repository


def handle_valuation(valuation: dict) -> None:
    trade_id = valuation.get("trade_id")
    if not trade_id:
        return

    payload = valuation.get("valuation_payload") or {}
    if bool(payload.get("final")):
        cache.trades.remove(trade_id)
        cache.drop_valuation(trade_id)
        return

    if cache.trades.get(trade_id) is None:
        try:
            loaded = repository.get_trade(trade_id)
        except Exception:
            logging.exception("Failed to lazy-load trade %s", trade_id)
            return
        if loaded is None or loaded.status != "ACTIVE":
            return
        cache.trades.add(loaded)

    cache.record_valuation(valuation)


def _trade_to_dict(trade) -> dict:
    return {
        "trade_id": trade.trade_id,
        "book_id": trade.book_id,
        "asset_class": trade.asset_class,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "trade_price": trade.trade_price,
        "currency": trade.currency,
        "status": trade.status,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "close_price": trade.close_price,
        "close_reason": trade.close_reason,
    }


def _live_valuation(trade_id: str) -> dict | None:
    valuation = cache.get_valuation(trade_id)
    if valuation is not None:
        return {
            "fair_value": valuation.get("fair_value"),
            "unrealized_pnl": valuation.get("unrealized_pnl"),
            "realized_pnl": valuation.get("realized_pnl"),
            "total_pnl": valuation.get("total_pnl"),
            "currency": valuation.get("currency"),
            "valuation_time": valuation.get("valuation_time"),
            "source": "valuation-stream",
        }
    history = repository.valuation_history(trade_id, limit=1)
    if not history:
        return None
    latest = history[0]
    return {
        "fair_value": latest.get("fair_value"),
        "unrealized_pnl": latest.get("unrealized_pnl"),
        "realized_pnl": latest.get("realized_pnl"),
        "total_pnl": latest.get("total_pnl"),
        "currency": latest.get("currency"),
        "valuation_time": latest.get("valuation_time"),
        "source": "valuations-db",
    }


def list_trades(*, book_id=None, asset_class=None, status=None, symbol=None,
                limit=100, offset=0) -> list[dict]:
    if status in (None, "ACTIVE"):
        trades = cache.trades.query(
            book_id=book_id, asset_class=asset_class, status="ACTIVE", symbol=symbol
        )
    else:
        trades = repository.list_trades(
            book_id=book_id, asset_class=asset_class, status=status, symbol=symbol,
            limit=limit, offset=offset,
        )
    result = []
    for trade in trades:
        row = _trade_to_dict(trade)
        row["latest_valuation"] = _live_valuation(trade.trade_id)
        result.append(row)
    return result


def trade_detail(trade_id: str) -> dict | None:
    trade = cache.trades.get(trade_id)
    if trade is None:
        trade = repository.get_trade(trade_id)
    if trade is None:
        return None
    return {
        "trade": _trade_to_dict(trade),
        "latest_valuation": _live_valuation(trade_id),
        "valuation_history": repository.valuation_history(trade_id),
        "audit_logs": repository.audit_logs(trade_id),
    }


def books_summary() -> list[dict]:
    books = repository.list_books()
    realized_by_book = repository.realized_pnl_by_book()
    summaries = []
    for book in books:
        book_id = book["book_id"]
        active = cache.trades.query(book_id=book_id, status="ACTIVE")
        unrealized = Decimal("0")
        for trade in active:
            valuation = cache.get_valuation(trade.trade_id)
            if valuation is not None:
                unrealized += valuation.get("unrealized_pnl") or Decimal("0")
        realized = realized_by_book.get(book_id) or Decimal("0")
        summaries.append({
            "book_id": book_id,
            "name": book["name"],
            "expected_asset_class": book["expected_asset_class"],
            "active_trades": len(active),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
            "currency": "USD",
        })
    return summaries
