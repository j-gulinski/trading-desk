import itertools
import time

from bottle import Bottle, response

from desk_runtime.http import json_response
from sample_core import call_stub, cpu_work, write_then_read

app = Bottle()


@app.get("/health")
def health():
    return json_response({"status": "ok"})


@app.get("/io")
def io():
    return json_response({"downstream": call_stub()})


@app.get("/cpu")
def cpu():
    return json_response({"digest": cpu_work()})


@app.post("/db")
def db():
    return json_response(write_then_read())


@app.get("/stream")
def stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")

    def events():
        for n in itertools.count():
            yield f"data: {n}\n\n"
            time.sleep(1)

    return events()
