import json
import logging
import urllib.request
import urllib.error

from app.config import TRADE_ACTIONS_URL


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
        logging.warning("Failed to submit %s intent: %s", intent.get("action_type"), e)
        return None
