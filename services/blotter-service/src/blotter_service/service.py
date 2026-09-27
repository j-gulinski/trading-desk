import json
from decimal import Decimal

from blotter_service import live_valuations, repository
from desk_domain import fx
from desk_domain.instruments import type_view_for

ZERO = Decimal("0")
METRICS = ("gross_entry", "unrealized", "realized", "total")


def _valuation_view(valuation: dict, source: str) -> dict:
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


def _live_valuation(trade: dict) -> dict | None:
    if trade["status"] != "ACTIVE":
        return None
    valuation = live_valuations.get(trade["trade_id"])
    return _valuation_view(valuation, "valuation-stream") if valuation else None


def list_trades(**filters) -> list[dict]:
    trades = repository.list_trades(**filters)
    for trade in trades:
        trade["latest_valuation"] = _live_valuation(trade)
    stored = repository.latest_valuations(
        [trade["trade_id"] for trade in trades if trade["latest_valuation"] is None]
    )
    for trade in trades:
        if trade["latest_valuation"] is None and trade["trade_id"] in stored:
            trade["latest_valuation"] = _valuation_view(stored[trade["trade_id"]], "valuations-db")
    return trades


def trade_detail(trade_id: str) -> dict | None:
    trade = repository.get_trade(trade_id)
    if trade is None:
        return None
    history = repository.valuation_history(trade_id)
    latest = _live_valuation(trade)
    if latest is None and history:
        latest = _valuation_view(history[0], "valuations-db")
    return {
        "trade": trade,
        "latest_valuation": latest,
        "valuation_history": history,
        "audit_logs": repository.audit_logs(trade_id),
    }


def _earliest(current, candidate):
    if candidate is None or (current is not None and current <= candidate):
        return current
    return candidate


STATUS_RANK = {"LIVE": 0, "MARKET_CLOSED": 1, "STALE": 2}


def _worse(current, candidate):
    return max(current, candidate or "STALE", key=lambda status: STATUS_RANK.get(status, 2))


def _positions(active: list[dict]) -> tuple[dict, dict, list[dict]]:
    """Net live positions of one book, plus gross entry and unrealized P&L per currency."""
    gross_entry: dict[str, Decimal] = {}
    unrealized: dict[str, Decimal] = {}
    by_position: dict[tuple, dict] = {}

    for trade in active:
        valuation = live_valuations.get(trade["trade_id"])
        provider = trade["market_data_provider"]
        if provider is None and valuation is not None:
            provider = valuation.get("market_data_provider")
        terms = trade["terms"]
        currency = trade["currency"]
        contract_key = json.dumps(terms, sort_keys=True, default=str)
        position = by_position.setdefault((trade["symbol"], currency, provider, contract_key), {
            "contract_key": contract_key,
            "symbol": trade["symbol"],
            "currency": currency,
            "asset_class": trade["asset_class"],
            **type_view_for(trade["asset_class"]),
            "market_data_provider": provider,
            "terms": terms,
            "trades": 0,
            "net_quantity": ZERO,
            "gross_quantity": ZERO,
            "entry_cost": ZERO,
            "unrealized_pnl": ZERO,
            "current_price": None,
            "valuation_time": None,
            "oldest_valuation_time": None,
            "market_data_timestamp": None,
            "oldest_market_data_timestamp": None,
            "valuation_payload": {},
            "status": "LIVE",
            "stale_at": None,
            "unvalued": 0,
        })
        quantity = trade["quantity"]
        price = trade["trade_price"]
        multiplier = int(terms.get("multiplier", 1))
        gross_entry[currency] = (gross_entry.get(currency) or ZERO) + abs(quantity * price * multiplier)
        position["trades"] += 1
        position["net_quantity"] += -quantity if trade["side"] == "SELL" else quantity
        position["gross_quantity"] += abs(quantity)
        position["entry_cost"] += abs(quantity) * price

        if valuation is None:
            position["unvalued"] += 1
            continue
        trade_unrealized = valuation.get("unrealized_pnl") or ZERO
        unrealized[currency] = (unrealized.get(currency) or ZERO) + trade_unrealized
        position["unrealized_pnl"] += trade_unrealized
        valued_at = valuation.get("valuation_time")
        market_at = valuation.get("market_data_timestamp")
        state = valuation.get("valuation_payload") or {}
        position["status"] = _worse(position["status"], state.get("status"))
        position["stale_at"] = _earliest(position["stale_at"], state.get("stale_at"))
        position["oldest_valuation_time"] = _earliest(position["oldest_valuation_time"], valued_at)
        position["oldest_market_data_timestamp"] = _earliest(
            position["oldest_market_data_timestamp"], market_at
        )
        if valued_at is not None and (
            position["valuation_time"] is None or valued_at >= position["valuation_time"]
        ):
            payload = valuation.get("valuation_payload") or {}
            position["valuation_time"] = valued_at
            position["current_price"] = payload.get("current_price")
            position["market_data_timestamp"] = market_at
            position["valuation_payload"] = payload

    positions = sorted(
        by_position.values(),
        key=lambda p: (p["symbol"], p["market_data_provider"] or "", p["currency"] or ""),
    )
    for position in positions:
        if position["unvalued"] or position["valuation_time"] is None:
            position["status"] = "PENDING"
        gross = position.pop("gross_quantity")
        entry_cost = position.pop("entry_cost")
        position["average_entry"] = entry_cost / gross if gross else None
    return gross_entry, unrealized, positions


def _currency_subtotals(gross_entry: dict, unrealized: dict, realized: dict) -> list[dict]:
    return [
        {
            "currency": currency,
            "values": {
                "gross_entry": gross_entry.get(currency) or ZERO,
                "unrealized": unrealized.get(currency) or ZERO,
                "realized": realized.get(currency) or ZERO,
                "total": (unrealized.get(currency) or ZERO) + (realized.get(currency) or ZERO),
            },
        }
        for currency in sorted(set(gross_entry) | set(unrealized) | set(realized))
    ]


def _book_summary(book: dict, active: list[dict], closed: list[dict]) -> dict:
    gross_entry, unrealized, positions = _positions(active)
    realized = {row["currency"]: row["realized_pnl"] for row in closed}
    currencies = {trade["currency"] for trade in active} | set(realized)
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    realized_total = sum(realized.values(), ZERO)
    unrealized_total = sum(unrealized.values(), ZERO)
    return {
        "book_id": book["book_id"],
        "name": book["name"],
        "expected_asset_class": book["expected_asset_class"],
        **type_view_for(book["expected_asset_class"]),
        "is_active": book["is_active"],
        "active_trades": len(active),
        "closed_trades": sum(row["trades"] for row in closed),
        "gross_entry_value": sum(gross_entry.values(), ZERO) if currency else None,
        "realized_pnl": realized_total if currency else None,
        "unrealized_pnl": unrealized_total if currency else None,
        "total_pnl": realized_total + unrealized_total if currency else None,
        "currency": currency,
        "subtotals": _currency_subtotals(gross_entry, unrealized, realized),
        "positions": positions,
    }


def _portfolio_subtotals(books: list[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    for book in books:
        for row in book["subtotals"]:
            values = totals.setdefault(row["currency"], dict.fromkeys(METRICS, ZERO))
            for metric in METRICS:
                values[metric] += row["values"][metric]
    return [{"currency": currency, "values": totals[currency]} for currency in sorted(totals)]


def _conversions(currencies: list[str], currency: str | None) -> dict[str, dict]:
    if currency is None:
        return {}
    rates = fx.load_official_rates()
    return {code: fx.resolve_rate(code, currency, rates) for code in currencies}


def _fx_view(conversion: dict | None) -> dict | None:
    if conversion is None:
        return None
    if conversion["rate"] is None:
        return {"reason": conversion["reason"]}
    return {key: conversion[key] for key in ("rate", "path", "provider", "as_of")}


def _reported(subtotals: list[dict], currency: str | None, conversions: dict) -> dict:
    """Amounts in the reporting currency; all null when any currency cannot be converted."""
    if currency is None:
        if len(subtotals) != 1:
            return {"currency": None, **dict.fromkeys(METRICS), "excluded": []}
        return {"currency": subtotals[0]["currency"], **subtotals[0]["values"], "excluded": []}
    amounts = dict.fromkeys(METRICS, ZERO)
    excluded = []
    for row in subtotals:
        conversion = conversions[row["currency"]]
        if conversion["rate"] is None:
            excluded.append({"currency": row["currency"], "reason": conversion["reason"]})
            continue
        for metric in METRICS:
            amounts[metric] += row["values"][metric] * conversion["rate"]
    if excluded:
        amounts = dict.fromkeys(METRICS)
    return {"currency": currency, **amounts, "excluded": excluded}


def books_summary(currency: str | None = None) -> dict:
    active_by_book: dict[str, list[dict]] = {}
    for trade in repository.active_trades():
        active_by_book.setdefault(trade["book_id"], []).append(trade)
    closed_by_book: dict[str, list[dict]] = {}
    for row in repository.closed_trade_totals():
        closed_by_book.setdefault(row["book_id"], []).append(row)
    books = [
        _book_summary(
            book,
            active_by_book.get(book["book_id"], []),
            closed_by_book.get(book["book_id"], []),
        )
        for book in repository.list_books()
    ]
    subtotals = _portfolio_subtotals(books)
    conversions = _conversions([row["currency"] for row in subtotals], currency)
    for book in books:
        book["reported"] = _reported(book["subtotals"], currency, conversions)
    return {
        "currency": currency,
        "books": books,
        "portfolio": {
            "book_count": len(books),
            "active_trades": sum(book["active_trades"] for book in books),
            "closed_trades": sum(book["closed_trades"] for book in books),
            "subtotals": [
                {**row, "fx": _fx_view(conversions.get(row["currency"]))} for row in subtotals
            ],
            "reported": _reported(subtotals, currency, conversions),
        },
    }
