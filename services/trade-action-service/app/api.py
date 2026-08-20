import json
import uuid
import bottle
from bottle import request, response

from app import action_queue, trade_processor
from app.config import QUOTE_PROVIDER_CHOICES
from shared.active_set import load_active_set
from shared.db import session_scope
from shared.providers import supports_quotes
from shared.symbols import watchlist_spot_symbols
from shared.term_schemas import public_term_schemas

app = bottle.Bottle()

VALIDATED_ACTIONS = {
    "OPEN_TRADE": trade_processor.validate_open,
    "CLOSE_TRADE": trade_processor.validate_close,
}

QUEUED_ACTIONS = (*VALIDATED_ACTIONS, "REASSIGN_TRADES", "CLOSE_ALL")


def route(*paths, **kwargs):
    def decorate(handler):
        for path in paths:
            app.route(path, **kwargs)(handler)
        return handler
    return decorate


def _normalize(body):
    intent = dict(body or {})
    intent.setdefault("action_type", "OPEN_TRADE")
    if "client_seen_price" not in intent and intent.get("reference_price") is not None:
        intent["client_seen_price"] = str(intent.pop("reference_price"))
    return intent


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
        intent["trade_id"] = str(uuid.uuid4())
        ack["trade_id"] = intent["trade_id"]
    action_queue.enqueue(intent)
    return ack


def _rejection(intent):
    action = intent.get("action_type")
    if action not in QUEUED_ACTIONS:
        return f"unknown action type: {action}"
    validate = VALIDATED_ACTIONS.get(action)
    if validate is None:
        return None
    with session_scope() as session:
        _, error = validate(session, intent)
        if error is not None:
            trade_processor.audit_rejection(session, intent, error)
    return error


@app.route("/instruments")
def instruments():
    with session_scope() as session:
        items = [
            {"symbol": entry.symbol, "asset_class": entry.asset_class,
             "currency": entry.currency,
             "providers": sorted(
                 provider for provider in QUOTE_PROVIDER_CHOICES
                 if entry.serves(provider)
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
        underlying_choices = watchlist_spot_symbols(session)
    return _json(public_term_schemas(underlying_choices))


@route("/trade-actions", "/trades", method="POST")
def trade_action():
    intent = _normalize(request.json)
    error = _rejection(intent)
    if error is not None:
        return _json({"error": error}, 422)
    return _json(_accept(intent), 202)


@app.route("/trade-actions/batch", method="POST")
def trade_action_batch():
    accepted, rejected = [], []
    for item in (request.json or []):
        intent = _normalize(item)
        error = _rejection(intent)
        if error is not None:
            rejected.append({"client_request_id": intent.get("client_request_id"),
                             "error": error})
            continue
        accepted.append(_accept(intent))
    status = 202 if accepted else 422
    return _json({"accepted": len(accepted), "rejected": rejected}, status)


@app.route("/trade-actions/close-all", method="POST")
def trade_action_close_all():
    intent = dict(request.json or {})
    intent["action_type"] = "CLOSE_ALL"
    action_queue.enqueue(intent)
    return _json({"status": "accepted", "action_type": "CLOSE_ALL"}, 202)


@app.route("/queue/status")
def queue_status():
    return _json(action_queue.queue_status())
