from decimal import Decimal

from app import cache, repository
from app.config import SERVICE_NAME
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


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
            log.exception("lazy_load_failed", trade_id=trade_id)
            return
        if loaded is None or loaded.status != "ACTIVE":
            return
        cache.trades.add(loaded)
    else:
        book_id = valuation.get("book_id")
        if book_id and cache.trades.update_field(trade_id, "book_id", str(book_id)):
            log.info("trade_reindexed", trade_id=trade_id, book_id=str(book_id))

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
        "market_data_provider": trade.market_data_provider,
        "entry_price_timestamp": trade.entry_price_timestamp,
        "entry_snapshot_id": trade.entry_snapshot_id,
        "close_price_timestamp": trade.close_price_timestamp,
        "close_snapshot_id": trade.close_snapshot_id,
        "client_seen_price": trade.client_seen_price,
    }


def _live_valuation(trade_id: str) -> dict | None:
    valuation = cache.get_valuation(trade_id)
    source = "valuation-stream"
    if valuation is None:
        history = repository.valuation_history(trade_id, limit=1)
        if not history:
            return None
        valuation = history[0]
        source = "valuations-db"
    return {
        "fair_value": valuation.get("fair_value"),
        "unrealized_pnl": valuation.get("unrealized_pnl"),
        "realized_pnl": valuation.get("realized_pnl"),
        "total_pnl": valuation.get("total_pnl"),
        "currency": valuation.get("currency"),
        "valuation_time": valuation.get("valuation_time"),
        "source": source,
    }


def list_trades(*, book_id=None, asset_class=None, status=None, symbol=None,
                limit=100, offset=0) -> list[dict]:
    # ACTIVE rows come live from the valuation-stream cache; non-active rows from
    # the DB. With no status filter we return both (cache active + DB closed).
    trades = []
    if status in (None, "ACTIVE"):
        trades += cache.trades.query(
            book_id=book_id, asset_class=asset_class, status="ACTIVE", symbol=symbol
        )
    if status is None:
        trades += repository.list_trades(
            book_id=book_id, asset_class=asset_class, symbol=symbol,
            exclude_active=True, limit=limit, offset=offset,
        )
    elif status != "ACTIVE":
        trades += repository.list_trades(
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


def _net_positions(active) -> tuple[Decimal, list[dict]]:
    unrealized = Decimal("0")
    by_symbol: dict[str, dict] = {}

    for trade in active:
        position = by_symbol.setdefault(trade.symbol, {
            "symbol": trade.symbol,
            "asset_class": trade.asset_class,
            "trades": 0,
            "net_quantity": Decimal("0"),
            "gross_quantity": Decimal("0"),
            "entry_cost": Decimal("0"),
            "unrealized_pnl": Decimal("0"),
            "current_price": None,
            "valuation_time": None,
            "unvalued": 0,
        })
        quantity = trade.quantity or Decimal("0")
        position["trades"] += 1
        position["net_quantity"] += -quantity if trade.side == "SELL" else quantity
        position["gross_quantity"] += abs(quantity)
        position["entry_cost"] += abs(quantity) * (trade.trade_price or Decimal("0"))

        valuation = cache.get_valuation(trade.trade_id)
        if valuation is None:
            position["unvalued"] += 1
            continue
        trade_unrealized = valuation.get("unrealized_pnl") or Decimal("0")
        unrealized += trade_unrealized
        position["unrealized_pnl"] += trade_unrealized
        valued_at = valuation.get("valuation_time")
        if valued_at is not None and (
            position["valuation_time"] is None or valued_at >= position["valuation_time"]
        ):
            position["valuation_time"] = valued_at
            position["current_price"] = (valuation.get("valuation_payload") or {}).get(
                "current_price"
            )

    positions = []
    for position in sorted(by_symbol.values(), key=lambda p: p["symbol"]):
        gross = position.pop("gross_quantity")
        entry_cost = position.pop("entry_cost")
        position["average_entry"] = entry_cost / gross if gross else None
        positions.append(position)
    return unrealized, positions


def books_summary() -> list[dict]:
    books = repository.list_books()
    realized_by_book = repository.realized_pnl_by_book()
    closed_by_book = repository.closed_trade_counts_by_book()
    currencies_by_book = repository.trade_currencies_by_book()
    summaries = []
    for book in books:
        book_id = book["book_id"]
        active = cache.trades.query(book_id=book_id, status="ACTIVE")
        unrealized, positions = _net_positions(active)
        realized = realized_by_book.get(book_id) or Decimal("0")
        currencies = currencies_by_book.get(book_id) or set()
        summaries.append({
            "book_id": book_id,
            "name": book["name"],
            "expected_asset_class": book["expected_asset_class"],
            "is_active": book["is_active"],
            "active_trades": len(active),
            "closed_trades": closed_by_book.get(book_id, 0),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "positions": positions,
        })
    return summaries
