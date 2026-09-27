import structlog
from sqlalchemy.exc import IntegrityError

from trade_action_service import repository
from trade_action_service.config import SERVICE_NAME
from trade_action_service.trade_validation import validate_close, validate_open, validate_reassign
from desk_domain.contract_data import with_close_metadata
from desk_domain.audit import write_audit
from desk_runtime.db import session_scope
from desk_runtime.logging_config import get_logger


log = get_logger(SERVICE_NAME)

REJECTION_LABELS = {"OPEN_TRADE": "Open", "CLOSE_TRADE": "Close", "REASSIGN_TRADES": "Reassign"}
PLAN_ERRORS = (ValueError, TypeError, ArithmeticError)


def _audit(session, event_type, message, intent, severity="INFO", payload=None,
           entity_type="TRADE", entity_id=None):
    write_audit(
        SERVICE_NAME,
        event_type,
        message,
        entity_type=entity_type,
        entity_id=entity_id or intent.get("trade_id"),
        correlation_id=intent.get("client_request_id"),
        severity=severity,
        payload=payload,
        session=session,
    )


def _rejection(session, intent, reason):
    action = intent["action_type"]
    log.warning("intent_rejected", action=action, reason=reason, symbol=intent.get("symbol"),
                book_id=intent.get("book_id"), trade_id=intent.get("trade_id"))
    reassign = action == "REASSIGN_TRADES"
    _audit(
        session, "ACTION_REJECTED", f"{REJECTION_LABELS[action]} rejected: {reason}", intent,
        severity="WARNING",
        payload={
            "reason": reason,
            "provider": intent.get("market_data_provider"),
            "symbol": intent.get("symbol"),
            "client_seen_price": intent.get("client_seen_price"),
        },
        entity_type="BOOK" if reassign else "TRADE",
        entity_id=intent.get("book_id") if reassign else None,
    )
    return 422, {"error": reason}


def _opened(trade_id, request_id, price, replay=False):
    body = {"status": "opened", "trade_id": str(trade_id), "client_request_id": request_id,
            "executed_price": str(price)}
    return (200, {**body, "idempotent_replay": True}) if replay else (201, body)


def _replay(request_id):
    with session_scope() as session:
        trade = repository.trade_by_client_request_id(session, request_id)
        return _opened(trade.trade_id, request_id, trade.trade_price, replay=True)


def open_trade(intent):
    request_id = intent["client_request_id"]
    try:
        with session_scope() as session:
            existing = repository.trade_by_client_request_id(session, request_id)
            if existing is not None:
                return _opened(existing.trade_id, request_id, existing.trade_price, replay=True)
            try:
                plan = validate_open(session, intent)
                with session.begin_nested():
                    repository.insert_trade(
                        session, intent, plan["instrument"], plan["provider"],
                        plan["price"], plan["quote"],
                    )
            except PLAN_ERRORS as error:
                return _rejection(session, intent, str(error))
            quote, price = plan["quote"], plan["price"]
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
    except IntegrityError:
        log.info("duplicate_open_replayed", client_request_id=request_id)
        return _replay(request_id)
    log.info("trade_created", trade_id=intent["trade_id"], symbol=intent.get("symbol"),
             book_id=intent.get("book_id"), side=intent.get("side"),
             quantity=intent.get("quantity"), provider=plan["provider"],
             executed_price=str(price))
    return _opened(intent["trade_id"], request_id, price)


def close_trade(intent):
    with session_scope() as session:
        try:
            plan = validate_close(session, intent)
        except PLAN_ERRORS as error:
            return _rejection(session, intent, str(error))
        trade, quote, price = plan["trade"], plan["quote"], plan["price"]
        metadata = with_close_metadata(trade.trade_metadata, plan.get("close_provenance") or {})
        closed = repository.close_trade(session, trade.trade_id, price,
                                        intent.get("close_reason"), quote, metadata)
        if not closed:
            return _rejection(session, intent, "trade is not open")
        _audit(session, "TRADE_CLOSED", "Trade closed", intent, payload={
            "provider": plan["provider"], "symbol": trade.instrument.symbol,
            "freshness": quote.state.value, "close_price": str(price),
            "client_seen_price": intent.get("client_seen_price"),
            "close_reason": intent.get("close_reason"),
            "quote_timestamp": quote.provider_timestamp.isoformat() if quote.provider_timestamp else None,
            "snapshot_id": str(quote.snapshot_id) if quote.snapshot_id else None,
        })
    log.info("trade_closed", trade_id=intent["trade_id"], provider=plan["provider"],
             close_price=str(price), close_reason=intent.get("close_reason"))
    return 200, {"status": "closed", "trade_id": intent["trade_id"], "close_price": str(price)}


def reassign_trades(intent):
    with session_scope() as session:
        try:
            source, target = validate_reassign(session, intent)
        except PLAN_ERRORS as error:
            return _rejection(session, intent, str(error))
        target_name = target.name
        trade_ids = repository.reassign_active_trades(session, source.book_id, target.book_id)
        for trade_id in trade_ids:
            _audit(session, "TRADE_REASSIGNED", f"Trade moved from {source.name} to {target_name}",
                   intent, entity_id=str(trade_id), payload={
                       "from_book_id": str(source.book_id),
                       "to_book_id": str(target.book_id),
                   })
    log.info("trades_reassigned", count=len(trade_ids), from_book_id=intent["book_id"],
             to_book_id=intent["target_book_id"])
    return 200, {"status": "reassigned", "moved": len(trade_ids), "target_book": target_name}


HANDLERS = {
    "OPEN_TRADE": open_trade,
    "CLOSE_TRADE": close_trade,
    "REASSIGN_TRADES": reassign_trades,
}


def execute(intent):
    """Run one trade action in one transaction and return (status, body)."""
    structlog.contextvars.bind_contextvars(correlation_id=intent.get("client_request_id"))
    try:
        return HANDLERS[intent["action_type"]](intent)
    finally:
        structlog.contextvars.unbind_contextvars("correlation_id")
