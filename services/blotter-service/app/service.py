import json
from decimal import Decimal

from app import cache, repository
from app.config import SERVICE_NAME
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.logging_config import get_logger
from shared.symbols import SPOT_ASSET_CLASSES

log = get_logger(SERVICE_NAME)


def reconcile_valuations(rows: list[dict]) -> None:
    with cache.reconciliation_lock:
        active_ids = {trade.trade_id for trade in cache.trades.query()}
        cache.replace_valuations(rows, active_ids)
    log.info("valuations_reconciled", valuations=len(rows), active_trades=len(active_ids))


def handle_valuation(valuation: dict) -> None:
    with cache.reconciliation_lock:
        _handle_valuation(valuation)


def _handle_valuation(valuation: dict) -> None:
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
        "source": trade.source,
        "created_by_service": trade.created_by_service,
        "terms": trade.terms,
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
        "market_data_provider": valuation.get("market_data_provider"),
        "market_data_timestamp": valuation.get("market_data_timestamp"),
        "valuation_payload": valuation.get("valuation_payload") or {},
        "source": source,
    }


def list_trades(*, book_id=None, asset_class=None, status=None, symbol=None,
                limit=100, offset=0) -> list[dict]:
    # ACTIVE rows come live from the valuation-stream cache; non-active rows from
    # the DB. With no status filter we return both (cache active + DB closed).
    trades = []
    if status in (None, "ACTIVE"):
        active = cache.trades.query(
            book_id=book_id, asset_class=asset_class, status="ACTIVE", symbol=symbol
        )
        active.sort(key=lambda trade: str(trade.opened_at or ""), reverse=True)
        trades += active if status is None else active[offset:offset + limit]
    if status is None:
        trades += repository.list_trades(
            book_id=book_id, asset_class=asset_class, symbol=symbol,
            exclude_active=True, limit=limit + offset, offset=0,
        )
    elif status != "ACTIVE":
        trades += repository.list_trades(
            book_id=book_id, asset_class=asset_class, status=status, symbol=symbol,
            limit=limit, offset=offset,
        )
    if status is None:
        trades.sort(key=lambda trade: str(trade.opened_at or ""), reverse=True)
        trades = trades[offset:offset + limit]
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


def _net_positions(active) -> tuple[Decimal, dict, Decimal, dict, list[dict]]:
    unrealized = Decimal("0")
    unrealized_by_currency: dict[str, Decimal] = {}
    gross_entry = Decimal("0")
    gross_entry_by_currency: dict[str, Decimal] = {}
    by_position: dict[tuple[str, str, str | None, str], dict] = {}

    for trade in active:
        valuation = cache.get_valuation(trade.trade_id)
        provider = trade.market_data_provider
        if provider is None and trade.asset_class in (
            *SPOT_ASSET_CLASSES, "EUROPEAN_OPTION"
        ):
            provider = DEFAULT_QUOTE_PROVIDER
        if provider is None and valuation is not None:
            provider = valuation.get("market_data_provider")
        contract_key = json.dumps(trade.terms or {}, sort_keys=True, default=str)
        position_key = (trade.symbol, trade.currency, provider, contract_key)
        position = by_position.setdefault(position_key, {
            "contract_key": contract_key,
            "symbol": trade.symbol,
            "currency": trade.currency,
            "asset_class": trade.asset_class,
            "market_data_provider": provider,
            "terms": dict(trade.terms or {}),
            "trades": 0,
            "net_quantity": Decimal("0"),
            "gross_quantity": Decimal("0"),
            "entry_cost": Decimal("0"),
            "unrealized_pnl": Decimal("0"),
            "current_price": None,
            "valuation_time": None,
            "oldest_valuation_time": None,
            "market_data_timestamp": None,
            "oldest_market_data_timestamp": None,
            "valuation_payload": {},
            "unvalued": 0,
        })
        quantity = trade.quantity or Decimal("0")
        multiplier = int((trade.terms or {}).get("multiplier", 1))
        trade_gross_entry = abs(quantity * (trade.trade_price or Decimal("0")) * multiplier)
        gross_entry += trade_gross_entry
        gross_entry_by_currency[trade.currency] = (
            gross_entry_by_currency.get(trade.currency) or Decimal("0")
        ) + trade_gross_entry
        position["trades"] += 1
        position["net_quantity"] += -quantity if trade.side == "SELL" else quantity
        position["gross_quantity"] += abs(quantity)
        position["entry_cost"] += abs(quantity) * (trade.trade_price or Decimal("0"))

        if valuation is None:
            position["unvalued"] += 1
            continue
        trade_unrealized = valuation.get("unrealized_pnl") or Decimal("0")
        unrealized += trade_unrealized
        unrealized_by_currency[trade.currency] = (
            unrealized_by_currency.get(trade.currency) or Decimal("0")
        ) + trade_unrealized
        position["unrealized_pnl"] += trade_unrealized
        valued_at = valuation.get("valuation_time")
        if valued_at is not None and (
            position["oldest_valuation_time"] is None
            or valued_at < position["oldest_valuation_time"]
        ):
            position["oldest_valuation_time"] = valued_at
        market_at = valuation.get("market_data_timestamp")
        if market_at is not None and (
            position["oldest_market_data_timestamp"] is None
            or market_at < position["oldest_market_data_timestamp"]
        ):
            position["oldest_market_data_timestamp"] = market_at
        if valued_at is not None and (
            position["valuation_time"] is None or valued_at >= position["valuation_time"]
        ):
            position["valuation_time"] = valued_at
            position["current_price"] = (valuation.get("valuation_payload") or {}).get(
                "current_price"
            )
            position["market_data_timestamp"] = market_at
            position["valuation_payload"] = valuation.get("valuation_payload") or {}

    positions = []
    for position in sorted(
        by_position.values(),
        key=lambda p: (
            p["symbol"], p["market_data_provider"] or "", p["currency"] or ""
        ),
    ):
        gross = position.pop("gross_quantity")
        entry_cost = position.pop("entry_cost")
        position["average_entry"] = entry_cost / gross if gross else None
        positions.append(position)
    return (
        gross_entry,
        gross_entry_by_currency,
        unrealized,
        unrealized_by_currency,
        positions,
    )


def _currency_subtotals(gross_entry, unrealized, realized) -> list[dict]:
    return [
        {
            "currency": currency,
            "values": {
                "gross_entry": gross_entry.get(currency) or Decimal("0"),
                "unrealized": unrealized.get(currency) or Decimal("0"),
                "realized": realized.get(currency) or Decimal("0"),
                "total": (
                    (unrealized.get(currency) or Decimal("0"))
                    + (realized.get(currency) or Decimal("0"))
                ),
            },
        }
        for currency in sorted(set(gross_entry) | set(unrealized) | set(realized))
    ]


def books_summary() -> list[dict]:
    books = repository.list_books()
    realized_by_book = repository.realized_pnl_by_book()
    closed_by_book = repository.closed_trade_counts_by_book()
    currencies_by_book = repository.trade_currencies_by_book()
    summaries = []
    for book in books:
        book_id = book["book_id"]
        active = cache.trades.query(book_id=book_id, status="ACTIVE")
        (
            gross_entry,
            gross_entry_by_currency,
            unrealized,
            unrealized_by_currency,
            positions,
        ) = _net_positions(active)
        realized_by_currency = realized_by_book.get(book_id) or {}
        realized = sum(realized_by_currency.values(), Decimal("0"))
        currencies = currencies_by_book.get(book_id) or set()
        one_currency = len(currencies) == 1
        summaries.append({
            "book_id": book_id,
            "name": book["name"],
            "expected_asset_class": book["expected_asset_class"],
            "is_active": book["is_active"],
            "active_trades": len(active),
            "closed_trades": closed_by_book.get(book_id, 0),
            "gross_entry_value": gross_entry if one_currency else None,
            "realized_pnl": realized if one_currency else None,
            "unrealized_pnl": unrealized if one_currency else None,
            "total_pnl": realized + unrealized if one_currency else None,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "subtotals": _currency_subtotals(
                gross_entry_by_currency,
                unrealized_by_currency,
                realized_by_currency,
            ),
            "positions": positions,
        })
    return summaries
