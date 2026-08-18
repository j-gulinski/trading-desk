import json
import uuid
import bottle
from bottle import request, response

from app import action_queue
from app.config import SERVICE_NAME
from shared.db import session_scope
from shared.symbols import watchlist_items, watchlist_spot_symbols
from shared.term_schemas import public_term_schemas

app = bottle.Bottle()


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


@app.route("/instruments")
def instruments():
    with session_scope() as session:
        items = [
            {"symbol": item.symbol, "asset_class": item.asset_class,
             "currency": item.currency}
            for item in watchlist_items(session)
        ]
    return _json(items)


@app.route("/instruments/term-schemas")
def term_schemas():
    with session_scope() as session:
        underlying_choices = watchlist_spot_symbols(session)
    return _json(public_term_schemas(underlying_choices))


@app.route("/trade-actions", method="POST")
def trade_action():
    return _json(_accept(dict(request.json or {})), 202)


@app.route("/trade-actions/batch", method="POST")
def trade_action_batch():
    acks = [_accept(dict(item)) for item in (request.json or [])]
    return _json({"accepted": len(acks)}, 202)


@app.route("/trade-actions/close-all", method="POST")
def trade_action_close_all():
    intent = dict(request.json or {})
    intent["action_type"] = "CLOSE_ALL"
    action_queue.enqueue(intent)
    return _json({"status": "accepted", "action_type": "CLOSE_ALL"}, 202)


@app.route("/queue/status")
def queue_status():
    return _json(action_queue.queue_status())
