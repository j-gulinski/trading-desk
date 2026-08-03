import datetime
import json

import bottle
from bottle import request, response

from app import monitor, repository
from app.config import SERVICE_NAME
from shared.audit import write_audit
from shared.enums import Severity
from shared.serialization import to_json

app = bottle.Bottle()

VALID_SEVERITIES = {s.value for s in Severity}


def _parse_since(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_list(value):
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()] or None


def _parse_severities(value):
    wanted = _parse_list(value)
    if wanted is None:
        return None
    return [v.upper() for v in wanted if v.upper() in VALID_SEVERITIES] or None


@app.route("/health")
def health():
    return {"service": SERVICE_NAME, "status": "UP"}


@app.route("/status")
def status():
    response.content_type = "application/json"
    return json.dumps(monitor.get_state())


@app.route("/audits")
def audits():
    response.content_type = "application/json"
    limit = request.query.get("limit")
    rows = repository.recent_audits(
        limit=int(limit) if limit else repository.DEFAULT_LIMIT,
        since=_parse_since(request.query.get("since")),
        severities=_parse_severities(request.query.get("severity")),
        services=_parse_list(request.query.get("service")),
        event_types=_parse_list(request.query.get("event_type")),
    )
    return to_json(rows)


@app.route("/debug/audit", method="POST")
def debug_audit():
    # Test hook: write one real audit row (DB is up, so it persists) to exercise
    # the Errors & Warnings panel without a real fault. Defaults to a clearly
    # labelled TEST_EVENT / ERROR; severity and message are overridable.
    response.content_type = "application/json"
    body = request.json or {}
    severity = str(body.get("severity", "ERROR")).upper()
    if severity not in VALID_SEVERITIES:
        response.status = 400
        return to_json({"error": "invalid severity", "valid": sorted(VALID_SEVERITIES)})

    event_type = body.get("event_type") or "TEST_EVENT"
    message = body.get("message") or f"[TEST] synthetic {severity} event"
    write_audit(SERVICE_NAME, event_type, message, severity=severity)
    response.status = 201
    return to_json({"written": {"event_type": event_type, "severity": severity, "message": message}})
