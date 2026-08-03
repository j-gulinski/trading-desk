import bottle
from bottle import request, response

from app import generator
from app.config import SERVICE_NAME
from shared.serialization import to_json

app = bottle.Bottle()


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


@app.route("/health")
def health():
    return _json({"service": SERVICE_NAME, "status": "UP"})


@app.route("/generate-once", method="POST")
def generate_once():
    intent = generator.generate_once()
    if intent is None:
        return _json({"status": "skipped"}, 200)
    return _json({"status": "submitted", "intent": intent}, 202)


@app.route("/start", method="POST")
def start():
    generator.start()
    return _json(generator.status())


@app.route("/stop", method="POST")
def stop():
    generator.stop()
    return _json(generator.status())


@app.route("/status")
def status():
    return _json(generator.status())


@app.route("/config", method="GET")
def get_config():
    return _json(generator.get_config())


@app.route("/config", method="POST")
def set_config():
    body = request.json or {}
    fields = {key: body[key] for key in ("interval_ms", "target_open_trades") if key in body}
    if not fields:
        return _json({"error": "expected interval_ms and/or target_open_trades"}, 400)
    try:
        applied = generator.set_config(**fields)
    except (TypeError, ValueError):
        return _json({"error": "interval_ms and target_open_trades must be integers"}, 400)
    return _json(applied)
