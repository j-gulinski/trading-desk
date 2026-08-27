import json
import urllib.parse
import urllib.request

from desk_runtime.logging_config import get_logger
from books_service.config import BLOTTER_TRADES_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


class BlotterUnavailable(Exception):
    pass


def active_trade_count(book_id: str) -> int:
    if not BLOTTER_TRADES_URL:
        log.warning("blotter_url_missing")
        raise BlotterUnavailable("blotter url not configured")
    query = urllib.parse.urlencode({"book_id": book_id, "status": "ACTIVE"})
    try:
        with urllib.request.urlopen(f"{BLOTTER_TRADES_URL}?{query}", timeout=5) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log.warning("blotter_unreachable", book_id=book_id)
        raise BlotterUnavailable(str(exc)) from exc
    return len(rows) if isinstance(rows, list) else 0
