import json
import uuid
import bottle
from bottle import request, response

from app import action_queue, repository
from app.config import QUOTE_PROVIDER_CHOICES, TRADE_ACTION_BATCH_SIZE
from app.trade_handlers import audit_rejection
from app.trade_validation import validate_close, validate_open
from shared.active_set import load_active_set
from shared.curve_registry import latest_curve_sets
from shared.db import session_scope
from shared.providers import supports_quotes
from shared.symbols import watchlist_option_underlying_symbols
from shared.term_schemas import public_term_schemas

app = bottle.Bottle()

VALIDATED_ACTIONS = {
    "OPEN_TRADE": validate_open,
    "CLOSE_TRADE": validate_close,
}

QUEUED_ACTIONS = (*VALIDATED_ACTIONS, "REASSIGN_TRADES", "CLOSE_ALL")


def _normalize_text(intent, field, required=False):
    value = intent.get(field)
    if value is None:
        return f"{field} must be a non-empty string" if required else None
    if not isinstance(value, str) or not value.strip():
        return f"{field} must be a non-empty string"
    intent[field] = value.strip()
    return None


def _normalize_uuid(intent, field):
    try:
        intent[field] = str(uuid.UUID(str(intent.get(field))))
    except (AttributeError, TypeError, ValueError):
        return f"{field} must be a UUID"
    return None


def _normalize(body):
    if not isinstance(body, dict):
        return None, "request body must be an object"
    intent = dict(body)
    raw_action = intent.get("action_type", "OPEN_TRADE")
    if not isinstance(raw_action, str) or not raw_action.strip():
        return None, "action_type must be a non-empty string"
    action = raw_action.strip().upper()
    intent["action_type"] = action

    if action in QUEUED_ACTIONS:
        request_key_error = _normalize_text(
            intent,
            "client_request_id",
            required=action == "OPEN_TRADE",
        )
        if request_key_error is not None:
            return None, request_key_error

    if action == "OPEN_TRADE":
        intent.pop("trade_id", None)
        for field in ("asset_class", "side"):
            error = _normalize_text(intent, field, required=True)
            if error is not None:
                return None, error
        for field in ("symbol", "currency", "market_data_provider", "source"):
            if field in intent:
                error = _normalize_text(intent, field)
                if error is not None:
                    return None, error
        error = _normalize_uuid(intent, "book_id")
        if error is not None:
            return None, error
        intent["trade_id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"trading-desk:open:{intent['client_request_id']}",
            )
        )
    elif action == "CLOSE_TRADE":
        error = _normalize_uuid(intent, "trade_id")
        if error is not None:
            return None, error
        if "close_reason" in intent:
            error = _normalize_text(intent, "close_reason")
            if error is not None:
                return None, error
    elif action == "REASSIGN_TRADES":
        for field in ("book_id", "target_book_id"):
            error = _normalize_uuid(intent, field)
            if error is not None:
                return None, error
    elif action == "CLOSE_ALL" and "close_reason" in intent:
        error = _normalize_text(intent, "close_reason")
        if error is not None:
            return None, error
    return intent, None


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data)


def _accept(intent):
    ack = {
        "status": "accepted",
        "action_type": intent.get("action_type"),
        "client_request_id": intent.get("client_request_id"),
    }
    if intent.get("action_type") == "OPEN_TRADE":
        ack["trade_id"] = intent["trade_id"]
    return ack if action_queue.enqueue(intent) else None


def _idempotent_open_ack(intent):
    if intent.get("action_type") != "OPEN_TRADE":
        return None
    request_key = intent.get("client_request_id")
    trade_id = action_queue.accepted_trade_id(request_key)
    if trade_id is None:
        with session_scope() as session:
            existing = repository.trade_by_client_request_id(session, request_key)
            trade_id = str(existing.trade_id) if existing is not None else None
    if trade_id is None:
        return None
    return {
        "status": "accepted",
        "action_type": "OPEN_TRADE",
        "client_request_id": request_key,
        "trade_id": trade_id,
        "idempotent_replay": True,
    }


def _rejection(intent):
    action = intent.get("action_type")
    if action not in QUEUED_ACTIONS:
        return f"unknown action type: {action}"
    if action == "OPEN_TRADE" and not intent.get("client_request_id"):
        return "client_request_id is required for an idempotent open"
    validate = VALIDATED_ACTIONS.get(action)
    if validate is None:
        return None
    with session_scope() as session:
        _, error = validate(session, intent)
        if error is not None:
            audit_rejection(session, intent, error)
    return error


@app.route("/instruments")
def instruments():
    with session_scope() as session:
        items = [
            {"symbol": entry.symbol, "asset_class": entry.asset_class,
             "currency": entry.currency,
             "providers": sorted(
                 provider for provider in QUOTE_PROVIDER_CHOICES
                 if entry.serves_open(provider)
             ),
             "capabilities": {
                 provider: supports_quotes(provider, entry.asset_class)
                 for provider in QUOTE_PROVIDER_CHOICES
             }}
            for entry in load_active_set(session).values() if entry.tradeable
        ]
    return _json(sorted(items, key=lambda item: item["symbol"]))


@app.route("/instruments/term-schemas")
def term_schemas():
    with session_scope() as session:
        underlying_choices = watchlist_option_underlying_symbols(session)
        curves = latest_curve_sets(session)
    return _json({
        "schemas": public_term_schemas(underlying_choices, curves),
        "curves": curves,
    })


@app.route("/trade-actions", method="POST")
def trade_action():
    intent, normalize_error = _normalize(request.json)
    if normalize_error is not None:
        return _json({"error": normalize_error}, 400)
    replay = _idempotent_open_ack(intent)
    if replay is not None:
        return _json(replay, 202)
    error = _rejection(intent)
    if error is not None:
        return _json({"error": error}, 422)
    accepted = _accept(intent)
    if accepted is None:
        return _json({"error": "trade action queue is full; retry later"}, 503)
    return _json(accepted, 202)


@app.route("/trade-actions/batch", method="POST")
def trade_action_batch():
    body = request.json or []
    if not isinstance(body, list):
        return _json({"error": "batch body must be an array"}, 400)
    if len(body) > TRADE_ACTION_BATCH_SIZE:
        return _json({
            "error": f"batch cannot exceed {TRADE_ACTION_BATCH_SIZE} actions"
        }, 413)
    accepted, rejected = [], []
    for item in body:
        intent, normalize_error = _normalize(item)
        if normalize_error is not None:
            rejected.append({"client_request_id": None, "error": normalize_error})
            continue
        replay = _idempotent_open_ack(intent)
        if replay is not None:
            accepted.append(replay)
            continue
        error = _rejection(intent)
        if error is not None:
            rejected.append({"client_request_id": intent.get("client_request_id"),
                             "error": error})
            continue
        ack = _accept(intent)
        if ack is None:
            rejected.append({"client_request_id": intent.get("client_request_id"),
                             "error": "trade action queue is full; retry later"})
            continue
        accepted.append(ack)
    status = 202 if accepted else (503 if rejected and all(
        item["error"].startswith("trade action queue") for item in rejected
    ) else 422)
    return _json({"accepted": len(accepted), "rejected": rejected}, status)


@app.route("/trade-actions/close-all", method="POST")
def trade_action_close_all():
    raw_body = request.json
    if raw_body is not None and not isinstance(raw_body, dict):
        return _json({"error": "request body must be an object"}, 400)
    intent, normalize_error = _normalize({**(raw_body or {}), "action_type": "CLOSE_ALL"})
    if normalize_error is not None:
        return _json({"error": normalize_error}, 400)
    if not action_queue.enqueue(intent):
        return _json({"error": "trade action queue is full; retry later"}, 503)
    return _json({"status": "accepted", "action_type": "CLOSE_ALL"}, 202)


@app.route("/queue/status")
def queue_status():
    return _json(action_queue.queue_status())
