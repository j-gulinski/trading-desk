import bottle
from bottle import response

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
