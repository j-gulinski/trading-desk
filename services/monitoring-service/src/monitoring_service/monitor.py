import time
import json
import threading
import urllib.request
import urllib.error

from sqlalchemy import text

from desk_runtime.db import engine
from desk_runtime.functions import get_iso_timestamp
from desk_runtime.logging_config import get_logger
from desk_domain.audit import write_audit
from monitoring_service.config import TARGETS, POLL_INTERVAL_SECONDS, SERVICE_NAME

log = get_logger(SERVICE_NAME)
lock = threading.Lock()
state = {SERVICE_NAME: {"status": "UP"}}
_up_by_target = {}
_failures_by_target = {}

DB_TARGET_NAME = "postgres"


def _set(name, value):
    with lock:
        state[name] = value


def _note_transition(name, up, error=None):
    previous = _up_by_target.get(name)
    if up:
        _failures_by_target[name] = 0
        _up_by_target[name] = True
        if previous is False:
            log.info("dependency_recovered", target=name)
            write_audit(SERVICE_NAME, "DEPENDENCY_RECOVERED", f"{name} is back UP",
                        entity_type="SERVICE", entity_id=name)
        return True
    failures = _failures_by_target.get(name, 0) + 1
    _failures_by_target[name] = failures
    if failures < 3 or previous is False:
        return previous is False
    _up_by_target[name] = False
    log.warning("dependency_down", target=name, error=error)
    write_audit(SERVICE_NAME, "DEPENDENCY_DOWN", f"{name} is DOWN: {error}",
                entity_type="SERVICE", entity_id=name, severity="ERROR")
    return True


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
            value = {"status": status, "response_time_ms": response_time_ms,
                     "last_checked": now}
            if _note_transition(name, status == "UP", error=f"status {status}"):
                _set(name, value)
        except Exception as e:
            if _note_transition(name, False, error=str(e)):
                _set(name, {"status": "DOWN", "last_checked": now, "error": str(e)})
        time.sleep(POLL_INTERVAL_SECONDS)


def _poll_db_loop():
    while True:
        start = time.time()
        now = get_iso_timestamp()
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            response_time_ms = int((time.time() - start) * 1000)
            _note_transition(DB_TARGET_NAME, True)
            _set(DB_TARGET_NAME, {"status": "UP", "response_time_ms": response_time_ms,
                                  "last_checked": now})
        except Exception as e:
            if _note_transition(DB_TARGET_NAME, False, error=type(e).__name__):
                _set(DB_TARGET_NAME, {"status": "DOWN", "last_checked": now,
                                      "error": str(e)})
        time.sleep(POLL_INTERVAL_SECONDS)


def start_monitors():
    threads = []
    for name, url in TARGETS.items():
        thread = threading.Thread(target=_poll_loop, args=(name, url), name=f"mon-{name}", daemon=True)
        thread.start()
        threads.append(thread)
    db_thread = threading.Thread(target=_poll_db_loop, name=f"mon-{DB_TARGET_NAME}", daemon=True)
    db_thread.start()
    threads.append(db_thread)
    log.info("monitors_started", count=len(threads))
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Monitoring started", payload={"targets": len(threads)})
    return threads
