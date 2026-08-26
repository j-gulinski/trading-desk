from sqlalchemy.exc import IntegrityError

from app import action_queue, repository
from app.config import SERVICE_NAME
from app.trade_validation import parse_uuid, validate_close, validate_open
from shared.audit import write_audit
from shared.db import session_scope
from shared.logging_config import get_logger


log = get_logger(SERVICE_NAME)


def _audit(session, event_type, message, intent, severity="INFO", payload=None):
    write_audit(
        SERVICE_NAME,
        event_type,
        message,
        entity_type="TRADE",
        entity_id=intent.get("trade_id"),
        correlation_id=intent.get("client_request_id"),
        severity=severity,
        payload=payload,
        session=session,
    )


def _rejection_payload(intent, message):
    return {
        "reason": message,
        "provider": intent.get("market_data_provider"),
        "symbol": intent.get("symbol"),
        "client_seen_price": intent.get("client_seen_price"),
    }


def audit_rejection(session, intent, error):
    action = "Close" if intent.get("action_type") == "CLOSE_TRADE" else "Open"
    log.warning(
        "intent_rejected",
        action=intent.get("action_type"),
        reason=error,
        symbol=intent.get("symbol"),
        book_id=intent.get("book_id"),
        trade_id=intent.get("trade_id"),
    )
    _audit(
        session,
        "ACTION_REJECTED",
        f"{action} rejected: {error}",
        intent,
        "WARNING",
        _rejection_payload(intent, error),
    )


def open_trade(intent):
    try:
        with session_scope() as session:
            plan, error = validate_open(session, intent)
            if error is not None:
                audit_rejection(session, intent, error)
                return action_queue.incr("rejected")
            quote, price = plan["quote"], plan["price"]
            repository.insert_trade(
                session,
                intent,
                plan["terms"],
                plan["provider"],
                price,
                quote,
            )
            _audit(
                session,
                "TRADE_CREATED",
                "Trade created",
                intent,
                payload={
                    "provider": plan["provider"],
                    "symbol": intent.get("symbol"),
                    "freshness": quote.state.value,
                    "executed_price": str(price),
                    "client_seen_price": intent.get("client_seen_price"),
                    "price_basis": quote.executed_basis(intent.get("side")),
                    "quote_timestamp": (
                        quote.provider_timestamp.isoformat()
                        if quote.provider_timestamp is not None
                        else None
                    ),
                    "snapshot_id": str(quote.snapshot_id) if quote.snapshot_id else None,
                },
            )
        log.info(
            "trade_created",
            trade_id=intent.get("trade_id"),
            symbol=intent.get("symbol"),
            book_id=intent.get("book_id"),
            side=intent.get("side"),
            quantity=intent.get("quantity"),
            provider=plan["provider"],
            executed_price=str(price),
        )
        action_queue.incr("created")
    except IntegrityError:
        log.warning("duplicate_intent", trade_id=intent.get("trade_id"))
        action_queue.incr("duplicates")


def close_trade(intent):
    with session_scope() as session:
        plan, error = validate_close(session, intent)
        if error is not None:
            audit_rejection(session, intent, error)
            return action_queue.incr("rejected")
        quote, price = plan["quote"], plan["price"]
        close_metadata = dict(plan["trade"].trade_metadata or {})
        close_metadata.update(plan.get("close_provenance") or {})
        repository.close_trade(
            session,
            plan["trade"].trade_id,
            price,
            intent.get("close_reason"),
            quote,
            close_metadata,
        )
        _audit(
            session,
            "TRADE_CLOSED",
            "Trade closed",
            intent,
            payload={
                "provider": plan["provider"],
                "symbol": plan["trade"].symbol,
                "freshness": quote.state.value,
                "close_price": str(price),
                "client_seen_price": intent.get("client_seen_price"),
                "close_reason": intent.get("close_reason"),
                "quote_timestamp": (
                    quote.provider_timestamp.isoformat()
                    if quote.provider_timestamp is not None
                    else None
                ),
                "snapshot_id": str(quote.snapshot_id) if quote.snapshot_id else None,
            },
        )
    log.info(
        "trade_closed",
        trade_id=intent.get("trade_id"),
        provider=plan["provider"],
        close_price=str(price),
        close_reason=intent.get("close_reason"),
    )
    action_queue.incr("closed")


def close_all_trades(intent):
    reason = intent.get("close_reason") or "CLOSE_ALL"
    closed, skipped = 0, []
    with session_scope() as session:
        for trade in repository.active_trades(session):
            plan, error = validate_close(
                session,
                {"trade_id": str(trade.trade_id), "close_reason": reason},
                require_seen=False,
            )
            if error is not None:
                skipped.append((str(trade.trade_id), error))
                continue
            close_metadata = dict(plan["trade"].trade_metadata or {})
            close_metadata.update(plan.get("close_provenance") or {})
            repository.close_trade(
                session,
                trade.trade_id,
                plan["price"],
                reason,
                plan["quote"],
                close_metadata,
            )
            write_audit(
                SERVICE_NAME,
                "TRADE_CLOSED",
                "Trade closed",
                entity_type="TRADE",
                entity_id=str(trade.trade_id),
                payload={
                    "close_reason": reason,
                    "provider": plan["provider"],
                    "close_price": str(plan["price"]),
                    "quote_timestamp": (
                        plan["quote"].provider_timestamp.isoformat()
                        if plan["quote"].provider_timestamp is not None
                        else None
                    ),
                    "snapshot_id": (
                        str(plan["quote"].snapshot_id)
                        if plan["quote"].snapshot_id
                        else None
                    ),
                },
                session=session,
            )
            closed += 1
        for trade_id, error in skipped:
            write_audit(
                SERVICE_NAME,
                "ACTION_REJECTED",
                f"Close rejected: {error}",
                entity_type="TRADE",
                entity_id=trade_id,
                severity="WARNING",
                payload={"reason": error, "close_reason": reason},
                session=session,
            )
    log.info("close_all_processed", closed=closed, skipped=len(skipped), close_reason=reason)
    action_queue.incr("closed", closed)
    if skipped:
        action_queue.incr("rejected", len(skipped))


def reassign_trades(intent):
    source_id = parse_uuid(intent.get("book_id"))
    target_id = parse_uuid(intent.get("target_book_id"))

    def reject(session, message):
        log.warning(
            "reassign_rejected",
            reason=message,
            book_id=str(source_id) if source_id else None,
            target_book_id=str(target_id) if target_id else None,
        )
        write_audit(
            SERVICE_NAME,
            "ACTION_REJECTED",
            message,
            entity_type="BOOK",
            entity_id=str(source_id) if source_id else None,
            correlation_id=intent.get("client_request_id"),
            severity="WARNING",
            session=session,
        )
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
            write_audit(
                SERVICE_NAME,
                "TRADE_REASSIGNED",
                f"Trade moved from {source.name} to {target.name}",
                entity_type="TRADE",
                entity_id=trade_id,
                payload={
                    "from_book_id": str(source_id),
                    "to_book_id": str(target_id),
                },
                correlation_id=intent.get("client_request_id"),
                session=session,
            )
    log.info(
        "trades_reassigned",
        count=len(trade_ids),
        from_book_id=str(source_id),
        to_book_id=str(target_id),
    )
    action_queue.incr("reassigned", len(trade_ids))


ACTION_HANDLERS = {
    "OPEN_TRADE": open_trade,
    "CLOSE_TRADE": close_trade,
    "CLOSE_ALL": close_all_trades,
    "REASSIGN_TRADES": reassign_trades,
}
