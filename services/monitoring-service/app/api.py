import datetime
import json

import bottle
from bottle import request, response

from app import log_collector, log_publisher, monitor, repository
from app.config import SERVICE_NAME
from shared.audit import write_audit
from shared.enums import Severity
from shared.serialization import to_json

app = bottle.Bottle()

VALID_SEVERITIES = {s.value for s in Severity}
VALID_LOG_LEVELS = set(log_collector.LEVELS)

LOGS_DEFAULT_LIMIT = 200
LOGS_MAX_LIMIT = 10_000


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
        correlation_id=request.query.get("correlation_id") or None,
        entity_id=request.query.get("entity_id") or None,
    )
    return to_json(rows)


@app.route("/logs")
def logs():
    response.content_type = "application/json"
    levels = _parse_list(request.query.get("level"))
    if levels is not None:
        levels = [level.lower() for level in levels]
        if any(level not in VALID_LOG_LEVELS for level in levels):
            response.status = 400
            return json.dumps({"error": "invalid level", "valid": sorted(VALID_LOG_LEVELS)})

    since_id = request.query.get("since_id")
    if since_id:
        try:
            since_id = int(since_id)
        except ValueError:
            response.status = 400
            return json.dumps({"error": "since_id must be an integer"})
        run_id = request.query.get("run_id")
        if run_id and run_id != log_collector.RUN_ID:
            since_id = None
    else:
        since_id = None

    try:
        limit = int(request.query.get("limit") or LOGS_DEFAULT_LIMIT)
    except ValueError:
        limit = LOGS_DEFAULT_LIMIT
    limit = max(1, min(limit, LOGS_MAX_LIMIT))

    lines = log_collector.snapshot(
        services=_parse_list(request.query.get("service")),
        levels=levels,
        since_id=since_id,
        q=request.query.get("q") or None,
        limit=limit,
    )
    meta = {"run_id": log_collector.RUN_ID, "services": log_collector.services_meta()}
    return json.dumps({"lines": lines, "meta": meta})


@app.route("/logs/stream")
def logs_stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    client_queue = log_publisher.register()

    def generate_events():
        yield f"event: run\ndata: {json.dumps({'run_id': log_collector.RUN_ID})}\n\n"
        try:
            while True:
                record = client_queue.get()
                yield f"event: log_line\ndata: {json.dumps(record)}\n\n"
        finally:
            log_publisher.unregister(client_queue)

    return generate_events()


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
