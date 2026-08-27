import datetime
import itertools
import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from desk_runtime.logging_config import get_logger
from monitoring_service import log_publisher
from monitoring_service.config import (
    LOG_BUFFER_LINES,
    LOG_DIR,
    LOG_MINUTE_BUCKETS,
    LOG_SCAN_INTERVAL_SECONDS,
    LOG_WARM_START_TAIL_BYTES,
    SERVICE_NAME,
)

log = get_logger(SERVICE_NAME)

LEVELS = ("debug", "info", "warning", "error", "critical")

RUN_ID = uuid.uuid4().hex[:12]

lock = threading.Lock()
_buffers = {}
_minutes = {}
_tails = {}
_ids = itertools.count(int(time.time() * 1_000_000))


def _parse(raw):
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"event": raw}
    return parsed if isinstance(parsed, dict) else {"event": raw}


def _minute_key():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(second=0, microsecond=0).isoformat()


def _bump_minute(service, level):
    buckets = _minutes.setdefault(service, deque(maxlen=LOG_MINUTE_BUCKETS))
    minute = _minute_key()
    if not buckets or buckets[-1]["t"] != minute:
        buckets.append({"t": minute, **{name: 0 for name in LEVELS}})
    buckets[-1][level] += 1


def _ingest(service, raw):
    parsed = _parse(raw)
    level = str(parsed.get("level", "info")).lower()
    if level not in LEVELS:
        level = "info"
    record = dict(parsed)
    record["level"] = level
    record["service"] = service
    with lock:
        record["id"] = next(_ids)
        _buffers.setdefault(service, deque(maxlen=LOG_BUFFER_LINES)).append(record)
        _bump_minute(service, level)
    log_publisher.publish_line(record)


def _seed_offset(path, size):
    if size <= LOG_WARM_START_TAIL_BYTES:
        return 0
    offset = size - LOG_WARM_START_TAIL_BYTES
    with path.open("rb") as handle:
        handle.seek(offset)
        cut = handle.read(LOG_WARM_START_TAIL_BYTES).find(b"\n")
    return size if cut < 0 else offset + cut + 1


def _scan_file(path, seed):
    key = str(path)
    stat = path.stat()
    tail = _tails.get(key)
    if tail is None:
        offset = _seed_offset(path, stat.st_size) if seed else 0
        tail = _tails[key] = {"inode": stat.st_ino, "offset": offset}
    elif stat.st_ino != tail["inode"] or stat.st_size < tail["offset"]:
        tail["inode"] = stat.st_ino
        tail["offset"] = 0
    if stat.st_size <= tail["offset"]:
        return
    with path.open("rb") as handle:
        handle.seek(tail["offset"])
        data = handle.read()
    end = data.rfind(b"\n")
    if end < 0:
        return
    tail["offset"] += end + 1
    service = path.stem
    for raw in data[:end].split(b"\n"):
        line = raw.decode("utf-8", errors="replace").strip()
        if line:
            _ingest(service, line)


def _scan(seed=False):
    for path in sorted(Path(LOG_DIR).glob("*.log")):
        try:
            _scan_file(path, seed)
        except OSError:
            continue
        except Exception:
            log.exception("log_scan_failed", file=path.name)


def _collector_loop():
    _scan(seed=True)
    with lock:
        _minutes.clear()
        seeded = sum(len(buffer) for buffer in _buffers.values())
    log.info("log_collector_started", log_dir=LOG_DIR, seeded_lines=seeded)
    while True:
        time.sleep(LOG_SCAN_INTERVAL_SECONDS)
        _scan()


def start_collector():
    if not LOG_DIR:
        log.warning("log_collector_disabled", reason="LOG_DIR not set")
        return None
    thread = threading.Thread(target=_collector_loop, name="log-collector", daemon=True)
    thread.start()
    return thread


SEARCH_KEYS = ("event", "message", "msg", "correlation_id", "trade_id", "book_id", "symbol")


def _matches(record, needle):
    for key in SEARCH_KEYS:
        value = record.get(key)
        if value is not None and needle in str(value).lower():
            return True
    return False


def snapshot(*, services=None, levels=None, since_id=None, q=None, limit=200):
    wanted_levels = set(levels) if levels else None
    needle = q.lower() if q else None
    with lock:
        pools = [
            list(buffer) for service, buffer in _buffers.items()
            if services is None or service in services
        ]
    lines = []
    for pool in pools:
        taken = 0
        # newest first, so a buffer can be abandoned as soon as limit is filled
        for record in reversed(pool):
            if since_id is not None and record["id"] <= since_id:
                break
            if wanted_levels is not None and record["level"] not in wanted_levels:
                continue
            if needle is not None and not _matches(record, needle):
                continue
            lines.append(record)
            taken += 1
            if taken == limit:
                break
    lines.sort(key=lambda record: (record.get("timestamp") or "", record["id"]), reverse=True)
    return lines[:limit]


def services_meta():
    with lock:
        meta = {}
        for service, buffer in sorted(_buffers.items()):
            counts = {name: 0 for name in LEVELS}
            for record in buffer:
                counts[record["level"]] += 1
            meta[service] = {
                "buffered": len(buffer),
                "last_at": buffer[-1].get("timestamp") if buffer else None,
                "counts": counts,
                "minutes": list(_minutes.get(service, [])),
            }
        return meta
