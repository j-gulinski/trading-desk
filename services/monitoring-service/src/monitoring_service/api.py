import datetime

import bottle
from bottle import response

from monitoring_service import log_collector, monitor, repository
from desk_domain.enums import Severity
from desk_runtime.http import json_error, json_response, query_text
from desk_runtime.serialization import to_json

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


@app.route("/status")
def status():
    return json_response(monitor.get_state())


@app.route("/audits")
def audits():
    try:
        limit = int(query_text("limit", repository.DEFAULT_LIMIT))
    except ValueError:
        return json_error("limit must be an integer", 400)
    return json_response(repository.recent_audits(
        limit=limit,
        since=_parse_since(query_text("since")),
        severities=_parse_severities(query_text("severity")),
        services=_parse_list(query_text("service")),
        event_types=_parse_list(query_text("event_type")),
        correlation_id=query_text("correlation_id"),
        entity_id=query_text("entity_id"),
    ))


@app.route("/logs")
def logs():
    levels = _parse_list(query_text("level"))
    if levels is not None:
        levels = [level.lower() for level in levels]
        if any(level not in VALID_LOG_LEVELS for level in levels):
            return json_error("invalid level", 400, valid=sorted(VALID_LOG_LEVELS))

    try:
        limit = int(query_text("limit", LOGS_DEFAULT_LIMIT))
    except ValueError:
        limit = LOGS_DEFAULT_LIMIT
    limit = max(1, min(limit, LOGS_MAX_LIMIT))

    lines = log_collector.snapshot(
        services=_parse_list(query_text("service")),
        levels=levels,
        q=query_text("q"),
        limit=limit,
    )
    return json_response({
        "lines": lines,
        "meta": {"run_id": log_collector.RUN_ID, "services": log_collector.services_meta()},
    })


@app.route("/logs/stream")
def logs_stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    return log_collector.hub.subscribe(
        first_frame=f"event: run\ndata: {to_json({'run_id': log_collector.RUN_ID})}\n\n"
    )
