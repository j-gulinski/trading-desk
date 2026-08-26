import time

import structlog

from app import action_queue
from app.config import SERVICE_NAME
from app.trade_handlers import ACTION_HANDLERS, audit_rejection
from shared.audit import write_audit
from shared.db import session_scope
from shared.logging_config import get_logger


log = get_logger(SERVICE_NAME)


def _process(intent):
    action = intent.get("action_type")
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        log.warning("unknown_action", action=action)
        with session_scope() as session:
            audit_rejection(session, intent, f"unknown action type: {action}")
        return action_queue.incr("rejected")
    handler(intent)


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
        log.info(
            "intent_dequeued",
            action=intent.get("action_type"),
            trade_id=intent.get("trade_id"),
        )
        try:
            _process(intent)
            if failing:
                failing = False
                log.info("worker_recovered")
                write_audit(
                    SERVICE_NAME,
                    "WORKER_RECOVERED",
                    "Trade-action worker processing again",
                    correlation_id=correlation_id,
                )
        except Exception as exc:
            log.exception(
                "process_failed",
                action=intent.get("action_type"),
                trade_id=intent.get("trade_id"),
            )
            if not failing:
                failing = True
                write_audit(
                    SERVICE_NAME,
                    "WORKER_FAILED",
                    f"Trade-action processing failed: {type(exc).__name__}",
                    correlation_id=correlation_id,
                    severity="ERROR",
                )
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")
            action_queue.record_processed(
                int((time.perf_counter() - started) * 1000)
            )
