import uuid
import bottle
from bottle import request

from trade_action_service.trade_handlers import HANDLERS, execute
from desk_domain.active_set import load_active_set
from desk_domain.curve_registry import latest_curve_sets
from desk_runtime.db import session_scope
from desk_domain.providers import QUOTE_PROVIDERS, supports_quotes
from desk_domain.symbols import watchlist_spot_catalog
from desk_domain.term_schemas import public_term_schemas
from desk_runtime.http import json_error, json_response

app = bottle.Bottle()


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
    if action not in HANDLERS:
        return None, f"unknown action type: {action}"
    request_key_error = _normalize_text(
        intent, "client_request_id", required=action == "OPEN_TRADE",
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
        intent["trade_id"] = str(uuid.uuid4())
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
    return intent, None


def _tradeable_instruments(session):
    return sorted(
        (
            {
                "symbol": entry.symbol,
                "asset_class": entry.asset_class,
                "currency": entry.currency,
                "providers": sorted(
                    provider for provider in QUOTE_PROVIDERS
                    if entry.serves_open(provider)
                ),
                "capabilities": {
                    provider: supports_quotes(provider, entry.asset_class)
                    for provider in QUOTE_PROVIDERS
                },
            }
            for entry in load_active_set(session).values() if entry.tradeable
        ),
        key=lambda item: item["symbol"],
    )


@app.route("/instruments/term-schemas")
def term_schemas():
    with session_scope() as session:
        spot_catalog = watchlist_spot_catalog(session)
        curves = latest_curve_sets(session)
        instruments = _tradeable_instruments(session)
    return json_response({
        "instruments": instruments,
        "schemas": public_term_schemas(spot_catalog, curves),
        "curves": curves,
    })


@app.route("/trade-actions", method="POST")
def trade_action():
    intent, normalize_error = _normalize(request.json)
    if normalize_error is not None:
        return json_error(normalize_error, 400)
    status, body = execute(intent)
    return json_response(body, status)
