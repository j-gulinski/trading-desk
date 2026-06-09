import json
import urllib.request
import urllib.error

from shared.logging_config import get_logger
from app.config import TRADE_ACTIONS_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


def submit(intent: dict) -> dict | None:
    data = json.dumps(intent).encode("utf-8")
    request = urllib.request.Request(
        TRADE_ACTIONS_URL, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        log.warning("submit_failed", action=intent.get("action_type"), error=str(e))
        return None
