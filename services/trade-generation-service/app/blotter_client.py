import json
import urllib.parse
import urllib.request

from shared.logging_config import get_logger
from app.config import BLOTTER_TRADES_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


def active_trades() -> dict:
    if not BLOTTER_TRADES_URL:
        log.warning("blotter_url_missing")
        return {}
    query = urllib.parse.urlencode({"status": "ACTIVE"})
    with urllib.request.urlopen(f"{BLOTTER_TRADES_URL}?{query}", timeout=10) as response:
        rows = json.loads(response.read().decode("utf-8"))
    return {
        str(row["trade_id"]): row["symbol"]
        for row in rows
        if row.get("trade_id") and row.get("symbol")
    }
