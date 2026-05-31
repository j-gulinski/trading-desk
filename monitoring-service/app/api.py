import json
import bottle
from bottle import response
from app.monitor import lock, monitoring_state

app = bottle.Bottle()


@app.route("/status")
def get_system_status():
    response.content_type = "application/json"
    with lock:
        return json.dumps(monitoring_state)


@app.route("/health")
def health():
    return {"service": "monitoring-service", "status": "UP"}
