import math
import time
import uuid
from datetime import datetime, time as day_time, timezone
from decimal import Decimal

import structlog
from sqlalchemy.exc import IntegrityError

from shared.active_set import load_active_set
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.curve_registry import latest_curve_sets, load_curve
from shared.db import session_scope
from shared.freshness import FreshnessState
from shared.pricing_math import bond_pv, european_option_pv, irs_pv
from shared.providers import supports_quotes
from shared.symbols import (
    CURVE_PRICED_ASSET_CLASSES,
    SPOT_ASSET_CLASSES,
    is_valid_symbol,
    watchlist_spot_currencies,
    watchlist_spot_symbols,
)
from shared.term_schemas import DEFAULT_VOLATILITY, validate_terms
from shared.audit import write_audit
from shared.logging_config import get_logger
from app import action_queue, market_state, repository
from app.config import (
    QUOTE_PROVIDER_CHOICES,
    SERVICE_NAME,
    TRADE_PRICE_TOLERANCE_PCT,
)

log = get_logger(SERVICE_NAME)


def _audit(session, event_type, message, intent, severity="INFO", payload=None):
    write_audit(SERVICE_NAME, event_type, message, entity_type="TRADE",
                entity_id=intent.get("trade_id"), correlation_id=intent.get("client_request_id"),
                severity=severity, payload=payload, session=session)


def _resolve_terms(session, intent, active, curves=()):
    asset_class = intent.get("asset_class")
    custom = intent.get("terms")
    if custom is not None:
        if not is_valid_symbol(intent.get("symbol")):
            return None, "invalid custom instrument symbol"
        return validate_terms(asset_class, custom, watchlist_spot_symbols(session),
                              curves, watchlist_spot_currencies(session))
    if asset_class in CURVE_PRICED_ASSET_CLASSES:
        return None, f"{asset_class} requires instrument terms"
    entry = active.get(intent.get("symbol"))
    if entry is None or entry.asset_class != asset_class or not entry.tradeable:
        return None, "symbol is not tradeable for this asset class"
    return {"asset_class": entry.asset_class, "currency": entry.currency}, None


def _resolve_provider(intent, active):
    asset_class = intent.get("asset_class")
    provider = intent.get("market_data_provider")
    symbol = intent.get("symbol")
    if asset_class not in SPOT_ASSET_CLASSES:
        return None, f"unsupported asset class {asset_class}"
    if not provider:
        return None, f"market data provider is required for {asset_class}"
    if provider not in QUOTE_PROVIDER_CHOICES:
        return None, f"unknown market data provider {provider}"
    if not supports_quotes(provider, asset_class):
        return None, f"{provider} cannot quote {asset_class}"
    entry = active.get(symbol)
    if entry is None or not entry.serves(provider):
        return None, f"{symbol} is not watched on {provider}"
    return provider, None


def _resolve_execution(session, intent, provider, side, allow_stale=False):
    symbol = intent.get("symbol")
    quote, state = market_state.current_quote(session, provider, symbol)
    if state is FreshnessState.MISSING:
        return None, None, f"{provider} has no current quote for {symbol}"
    if not allow_stale and state is FreshnessState.STALE:
        return quote, None, f"the {provider} quote for {symbol} is stale"
    price = quote.price_for(side)
    if price is None or price <= 0:
        return quote, None, f"{provider} has no usable price for {symbol}"
    deviation = market_state.deviation_percent(price, intent.get("client_seen_price"))
    if deviation is not None and deviation > TRADE_PRICE_TOLERANCE_PCT:
        return quote, None, (
            f"price moved {deviation:.2f}% from the {intent.get('client_seen_price')} "
            f"shown to you (limit {TRADE_PRICE_TOLERANCE_PCT}%)"
        )
    return quote, price, None


def _as_of_timestamp(as_of_text):
    return datetime.combine(
        datetime.strptime(as_of_text, "%Y-%m-%d").date(), day_time(0, 0),
        tzinfo=timezone.utc,
    )


def _load_terms_curves(terms):
    curves = {}
    for field in ("discount_curve", "projection_curve"):
        name = terms.get(field)
        if name is None:
            continue
        curve = load_curve(name)
        if curve is None:
            return None, f"no stored {name} curve set is available yet"
        curves[field] = curve
    return curves, None


def _model_price(terms, curves, underlying_mid=None):
    discount = curves["discount_curve"]
    if terms["asset_class"] == "IRS":
        value = irs_pv(terms, discount, curves.get("projection_curve"))
    elif terms["asset_class"] == "BOND":
        value = bond_pv(terms, discount)
    else:
        value = european_option_pv(
            terms, underlying_mid, discount,
            terms.get("volatility", DEFAULT_VOLATILITY),
        )
    return Decimal(str(value))


def _deviation_scale(terms, price):
    if terms["asset_class"] == "IRS":
        return Decimal(str(terms["notional"]))
    return abs(price)


def _model_deviation_error(terms, price, seen):
    if seen in (None, ""):
        return None
    scale = _deviation_scale(terms, price)
    if not scale:
        return None
    try:
        seen_price = Decimal(str(seen))
    except (ArithmeticError, ValueError):
        return None
    deviation = abs(price - seen_price) / scale * 100
    if deviation > Decimal(str(TRADE_PRICE_TOLERANCE_PCT)):
        return (
            f"model value moved {deviation:.2f}% of "
            f"{'notional' if terms['asset_class'] == 'IRS' else 'its value'} from the "
            f"{seen} shown to you (limit {TRADE_PRICE_TOLERANCE_PCT}%)"
        )
    return None


def _freeze_curve_provenance(terms, curves):
    for field, curve in curves.items():
        terms[f"{field}_provider"] = curve["provider"]
        terms[f"{field}_as_of"] = curve["as_of_date"]


def _validate_curve_open(session, intent, active, terms):
    asset_class = terms["asset_class"]
    if asset_class == "IRS":
        if intent.get("side") != "BUY":
            return None, "an IRS position is directed by its direction term — submit as BUY"
    elif intent.get("side") not in ("BUY", "SELL"):
        return None, "side must be BUY or SELL"
    if not market_state.is_parseable_price(intent.get("client_seen_price")):
        return None, "client_seen_price must be a number"
    curves, curve_error = _load_terms_curves(terms)
    if curve_error is not None:
        return None, curve_error

    underlying_quote = None
    provider = None
    if asset_class == "EUROPEAN_OPTION":
        underlying = terms["underlying_symbol"]
        entry = active.get(underlying)
        underlying_intent = {
            "asset_class": entry.asset_class if entry else "EQUITY",
            "market_data_provider": intent.get("market_data_provider"),
            "symbol": underlying,
        }
        provider, provider_error = _resolve_provider(underlying_intent, active)
        if provider_error is not None:
            return None, provider_error
        underlying_quote, state = market_state.current_quote(session, provider, underlying)
        if state is FreshnessState.MISSING:
            return None, f"{provider} has no current quote for {underlying}"
        if state is FreshnessState.STALE:
            return None, f"the {provider} quote for {underlying} is stale"

    price = _model_price(
        terms, curves,
        underlying_mid=underlying_quote.mid if underlying_quote else None,
    )
    deviation_error = _model_deviation_error(terms, price, intent.get("client_seen_price"))
    if deviation_error is not None:
        return None, deviation_error
    _freeze_curve_provenance(terms, curves)

    if underlying_quote is not None:
        quote = market_state.ModelQuote(
            terms["currency"], underlying_quote.state,
            provider_timestamp=underlying_quote.provider_timestamp,
            snapshot_id=underlying_quote.snapshot_id,
        )
    else:
        quote = market_state.ModelQuote(
            terms["currency"], FreshnessState.LIVE,
            provider_timestamp=_as_of_timestamp(curves["discount_curve"]["as_of_date"]),
        )
    return {"terms": terms, "provider": provider, "quote": quote, "price": price}, None


def validate_open(session, intent):
    book_id = _parse_uuid(intent.get("book_id"))
    book = repository.get_active_book(session, book_id) if book_id else None
    if book is None:
        return None, "unknown or inactive book"
    if book.expected_asset_class != intent.get("asset_class"):
        return None, (
            f"{book.name} takes {book.expected_asset_class}, "
            f"not {intent.get('asset_class')}"
        )
    asset_class = intent.get("asset_class")
    active = load_active_set(session)
    curves = latest_curve_sets(session) if asset_class in CURVE_PRICED_ASSET_CLASSES \
        else ()
    terms, term_error = _resolve_terms(session, intent, active, curves)
    if terms is None:
        return None, term_error
    quantity = intent.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) \
            or not math.isfinite(quantity) or quantity <= 0:
        return None, "quantity must be a positive number"
    if asset_class in CURVE_PRICED_ASSET_CLASSES:
        return _validate_curve_open(session, intent, active, terms)
    provider, provider_error = _resolve_provider(intent, active)
    if provider_error is not None:
        return None, provider_error
    if intent.get("side") not in ("BUY", "SELL"):
        return None, "side must be BUY or SELL"
    if not market_state.is_parseable_price(intent.get("client_seen_price")):
        return None, "client_seen_price must be a number"
    quote, price, execution_error = _resolve_execution(
        session, intent, provider, intent.get("side")
    )
    if execution_error is not None:
        return None, execution_error
    return {"terms": terms, "provider": provider, "quote": quote, "price": price}, None


def _rejection_payload(intent, message):
    return {
        "reason": message,
        "provider": intent.get("market_data_provider"),
        "symbol": intent.get("symbol"),
        "client_seen_price": intent.get("client_seen_price"),
    }


def audit_rejection(session, intent, error):
    action = "Close" if intent.get("action_type") == "CLOSE_TRADE" else "Open"
    log.warning("intent_rejected", action=intent.get("action_type"), reason=error,
                symbol=intent.get("symbol"), book_id=intent.get("book_id"),
                trade_id=intent.get("trade_id"))
    _audit(session, "ACTION_REJECTED", f"{action} rejected: {error}", intent,
           "WARNING", _rejection_payload(intent, error))


def _open(intent):
    try:
        with session_scope() as session:
            plan, error = validate_open(session, intent)
            if error is not None:
                audit_rejection(session, intent, error)
                return action_queue.incr("rejected")
            quote, price = plan["quote"], plan["price"]
            repository.insert_trade(session, intent, plan["terms"], plan["provider"],
                                    price, quote)
            _audit(session, "TRADE_CREATED", "Trade created", intent, payload={
                "provider": plan["provider"],
                "symbol": intent.get("symbol"),
                "freshness": quote.state.value,
                "executed_price": str(price),
                "client_seen_price": intent.get("client_seen_price"),
                "price_basis": quote.executed_basis(intent.get("side")),
                "quote_timestamp": (
                    quote.provider_timestamp.isoformat()
                    if quote.provider_timestamp is not None else None
                ),
                "snapshot_id": str(quote.snapshot_id) if quote.snapshot_id else None,
            })
        log.info("trade_created", trade_id=intent.get("trade_id"), symbol=intent.get("symbol"),
                 book_id=intent.get("book_id"), side=intent.get("side"),
                 quantity=intent.get("quantity"), provider=plan["provider"],
                 executed_price=str(price))
        action_queue.incr("created")
    except IntegrityError:
        log.warning("duplicate_intent", trade_id=intent.get("trade_id"))
        action_queue.incr("duplicates")


CLOSING_SIDE = {"BUY": "SELL", "SELL": "BUY"}


def _validate_curve_close(session, intent, trade):
    terms = dict(trade.trade_metadata or {})
    terms.setdefault("asset_class", trade.asset_class)
    curves, curve_error = _load_terms_curves(terms)
    if curve_error is not None:
        return None, curve_error
    provider = None
    underlying_quote = None
    if trade.asset_class == "EUROPEAN_OPTION":
        provider = trade.market_data_provider or DEFAULT_QUOTE_PROVIDER
        underlying = terms.get("underlying_symbol")
        underlying_quote, state = market_state.current_quote(session, provider, underlying)
        if state is FreshnessState.MISSING:
            return None, f"{provider} has no current quote for {underlying}"
    price = _model_price(
        terms, curves,
        underlying_mid=underlying_quote.mid if underlying_quote else None,
    )
    deviation_error = _model_deviation_error(terms, price, intent.get("client_seen_price"))
    if deviation_error is not None:
        return None, deviation_error
    if underlying_quote is not None:
        quote = market_state.ModelQuote(
            trade.trade_currency, underlying_quote.state,
            provider_timestamp=underlying_quote.provider_timestamp,
            snapshot_id=underlying_quote.snapshot_id,
        )
    else:
        quote = market_state.ModelQuote(
            trade.trade_currency, FreshnessState.LIVE,
            provider_timestamp=_as_of_timestamp(curves["discount_curve"]["as_of_date"]),
        )
    return {"trade": trade, "provider": provider, "quote": quote, "price": price}, None


def validate_close(session, intent):
    trade_id = _parse_uuid(intent.get("trade_id"))
    trade = repository.active_trade(session, trade_id) if trade_id else None
    if trade is None:
        return None, "trade is not open"
    if trade.asset_class in CURVE_PRICED_ASSET_CLASSES:
        return _validate_curve_close(session, intent, trade)
    provider = trade.market_data_provider or DEFAULT_QUOTE_PROVIDER
    quote, price, error = _resolve_execution(
        session, {**intent, "symbol": trade.symbol}, provider,
        CLOSING_SIDE.get(trade.side, "SELL"), allow_stale=True,
    )
    if error is not None:
        return None, error
    return {"trade": trade, "provider": provider, "quote": quote, "price": price}, None


def _close(intent):
    with session_scope() as session:
        plan, error = validate_close(session, intent)
        if error is not None:
            audit_rejection(session, intent, error)
            return action_queue.incr("rejected")
        quote, price = plan["quote"], plan["price"]
        repository.close_trade(
            session,
            plan["trade"].trade_id,
            price,
            intent.get("close_reason"),
            quote,
        )
        _audit(session, "TRADE_CLOSED", "Trade closed", intent, payload={
            "provider": plan["provider"],
            "symbol": plan["trade"].symbol,
            "freshness": quote.state.value,
            "close_price": str(price),
            "client_seen_price": intent.get("client_seen_price"),
            "close_reason": intent.get("close_reason"),
            "quote_timestamp": (
                quote.provider_timestamp.isoformat()
                if quote.provider_timestamp is not None else None
            ),
            "snapshot_id": str(quote.snapshot_id) if quote.snapshot_id else None,
        })
    log.info("trade_closed", trade_id=intent.get("trade_id"), provider=plan["provider"],
             close_price=str(price), close_reason=intent.get("close_reason"))
    action_queue.incr("closed")


def _close_all(intent):
    reason = intent.get("close_reason") or "CLOSE_ALL"
    closed, skipped = 0, []
    with session_scope() as session:
        for trade in repository.active_trades(session):
            plan, error = validate_close(
                session, {"trade_id": str(trade.trade_id), "close_reason": reason}
            )
            if error is not None:
                skipped.append((str(trade.trade_id), error))
                continue
            repository.close_trade(
                session,
                trade.trade_id,
                plan["price"],
                reason,
                plan["quote"],
            )
            write_audit(SERVICE_NAME, "TRADE_CLOSED", "Trade closed",
                        entity_type="TRADE", entity_id=str(trade.trade_id),
                        payload={"close_reason": reason, "provider": plan["provider"],
                                 "close_price": str(plan["price"]),
                                 "quote_timestamp": (
                                     plan["quote"].provider_timestamp.isoformat()
                                     if plan["quote"].provider_timestamp is not None else None
                                 ),
                                 "snapshot_id": (
                                     str(plan["quote"].snapshot_id)
                                     if plan["quote"].snapshot_id else None
                                 )}, session=session)
            closed += 1
        for trade_id, error in skipped:
            write_audit(SERVICE_NAME, "ACTION_REJECTED", f"Close rejected: {error}",
                        entity_type="TRADE", entity_id=trade_id,
                        severity="WARNING", payload={"reason": error, "close_reason": reason},
                        session=session)
    log.info("close_all_processed", closed=closed, skipped=len(skipped),
             close_reason=reason)
    action_queue.incr("closed", closed)
    if skipped:
        action_queue.incr("rejected", len(skipped))


def _reassign(intent):
    source_id = _parse_uuid(intent.get("book_id"))
    target_id = _parse_uuid(intent.get("target_book_id"))

    def reject(session, message):
        log.warning("reassign_rejected", reason=message,
                    book_id=str(source_id) if source_id else None,
                    target_book_id=str(target_id) if target_id else None)
        write_audit(SERVICE_NAME, "ACTION_REJECTED", message, entity_type="BOOK",
                    entity_id=str(source_id) if source_id else None,
                    correlation_id=intent.get("client_request_id"),
                    severity="WARNING", session=session)
        return action_queue.incr("rejected")

    with session_scope() as session:
        source = repository.get_book(session, source_id) if source_id else None
        target = repository.get_active_book(session, target_id) if target_id else None
        if source is None or target is None or source_id == target_id:
            return reject(session, "Reassign rejected: unknown or same book")
        if source.expected_asset_class != target.expected_asset_class:
            return reject(session, "Reassign rejected: asset class mismatch")
        trade_ids = repository.reassign_active_trades(session, source_id, target_id)
        for trade_id in trade_ids:
            write_audit(SERVICE_NAME, "TRADE_REASSIGNED",
                        f"Trade moved from {source.name} to {target.name}",
                        entity_type="TRADE", entity_id=trade_id,
                        payload={"from_book_id": str(source_id), "to_book_id": str(target_id)},
                        correlation_id=intent.get("client_request_id"), session=session)
    log.info("trades_reassigned", count=len(trade_ids),
             from_book_id=str(source_id), to_book_id=str(target_id))
    action_queue.incr("reassigned", len(trade_ids))


ACTIONS = {}


def _process(intent):
    action = intent.get("action_type")
    handler = ACTIONS.get(action)
    if handler is None:
        log.warning("unknown_action", action=action)
        with session_scope() as session:
            audit_rejection(session, intent, f"unknown action type: {action}")
        return action_queue.incr("rejected")
    handler(intent)


ACTIONS.update({
    "OPEN_TRADE": _open,
    "CLOSE_TRADE": _close,
    "CLOSE_ALL": _close_all,
    "REASSIGN_TRADES": _reassign,
})


def _parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def worker_loop():
    log.info("worker_started")
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Trade-action worker started")
    failing = False
    while True:
        intent = action_queue.intents.get()
        started = time.perf_counter()
        correlation_id = intent.get("client_request_id")
        if correlation_id:
            structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        log.info("intent_dequeued", action=intent.get("action_type"),
                 trade_id=intent.get("trade_id"))
        try:
            _process(intent)
            if failing:
                failing = False
                log.info("worker_recovered")
                write_audit(SERVICE_NAME, "WORKER_RECOVERED",
                            "Trade-action worker processing again",
                            correlation_id=correlation_id)
        except Exception as exc:
            log.exception("process_failed", action=intent.get("action_type"),
                          trade_id=intent.get("trade_id"))
            if not failing:
                failing = True
                write_audit(SERVICE_NAME, "WORKER_FAILED",
                            f"Trade-action processing failed: {type(exc).__name__}",
                            correlation_id=correlation_id, severity="ERROR")
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")
            action_queue.record_processed(int((time.perf_counter() - started) * 1000))
