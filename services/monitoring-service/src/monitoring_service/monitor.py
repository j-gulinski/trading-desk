import json
import threading
import time
import urllib.request
from functools import partial

from sqlalchemy import text

from desk_runtime.db import engine
from desk_runtime.functions import get_iso_timestamp
from desk_runtime.logging_config import get_logger
from desk_domain.audit import write_audit
from monitoring_service.config import TARGETS, POLL_INTERVAL_SECONDS, SERVICE_NAME

log = get_logger(SERVICE_NAME)
lock = threading.Lock()
state = {SERVICE_NAME: {"status": "UP"}}

DB_TARGET_NAME = "postgres"
FAILURES_BEFORE_DOWN = 3


def get_state():
    with lock:
        return dict(state)


def _service_status(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        try:
            return json.loads(response.read()).get("status", "UNKNOWN")
        except json.JSONDecodeError:
            return "UNKNOWN"


def _database_status():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return "UP"


def _watch(name, check):
    failures, down = 0, False
    while True:
        started = time.time()
        checked_at = get_iso_timestamp()
        try:
            status = check()
            entry = {"status": status, "response_time_ms": int((time.time() - started) * 1000),
                     "last_checked": checked_at}
            error = None if status == "UP" else f"status {status}"
        except Exception as exc:
            error = type(exc).__name__
            entry = {"status": "DOWN", "last_checked": checked_at, "error": str(exc)}
        with lock:
            state[name] = entry
        if error is None:
            failures = 0
            if down:
                down = False
                log.info("dependency_recovered", target=name)
                write_audit(SERVICE_NAME, "DEPENDENCY_RECOVERED", f"{name} is back UP",
                            entity_type="SERVICE", entity_id=name)
        else:
            failures += 1
            if failures >= FAILURES_BEFORE_DOWN and not down:
                down = True
                log.warning("dependency_down", target=name, error=error)
                write_audit(SERVICE_NAME, "DEPENDENCY_DOWN", f"{name} is DOWN: {error}",
                            entity_type="SERVICE", entity_id=name, severity="ERROR")
        time.sleep(POLL_INTERVAL_SECONDS)


def watchers():
    checks = {name: partial(_service_status, url) for name, url in TARGETS.items()}
    checks[DB_TARGET_NAME] = _database_status
    return [partial(_watch, name, check) for name, check in checks.items()]
