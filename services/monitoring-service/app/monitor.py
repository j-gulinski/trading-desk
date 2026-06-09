import time
import json
import threading
import urllib.request
import urllib.error

from shared.functions import get_iso_timestamp
from shared.logging_config import get_logger
from shared.audit import write_audit
from app.config import TARGETS, POLL_INTERVAL_SECONDS, SERVICE_NAME

log = get_logger(SERVICE_NAME)
lock = threading.Lock()
state = {SERVICE_NAME: {"status": "UP"}}


def _set(name, value):
    with lock:
        state[name] = value


def get_state():
    with lock:
        return dict(state)


def _poll_loop(name, url):
    while True:
        start = time.time()
        now = get_iso_timestamp()
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=3) as resp:
                body = resp.read()
            response_time_ms = int((time.time() - start) * 1000)
            try:
                status = json.loads(body.decode("utf-8")).get("status", "UNKNOWN")
            except json.JSONDecodeError:
                status = "UNKNOWN"
            _set(name, {"status": status, "response_time_ms": response_time_ms, "last_checked": now})
        except Exception as e:
            _set(name, {"status": "DOWN", "last_checked": now, "error": str(e)})
        time.sleep(POLL_INTERVAL_SECONDS)

def start_monitors():
    threads = []
    for name, url in TARGETS.items():
        thread = threading.Thread(target=_poll_loop, args=(name, url), name=f"mon-{name}", daemon=True)
        thread.start()
        threads.append(thread)
    log.info("monitors_started", count=len(threads))
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Monitoring started", payload={"targets": len(threads)})
    return threads
