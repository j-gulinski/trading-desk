import json
import bottle
from bottle import response

from app import monitor
from app.config import SERVICE_NAME

app = bottle.Bottle()


@app.route("/health")
def health():
    return {"service": SERVICE_NAME, "status": "UP"}


@app.route("/status")
def status():
    response.content_type = "application/json"
    return json.dumps(monitor.get_state())
