import json
import urllib.request
import urllib.error
from decimal import Decimal

from shared.pricing_math import bond_pv
from shared.logging_config import get_logger
from app.config import SNAPSHOT_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


def fetch_snapshot() -> dict | None:
    try:
        with urllib.request.urlopen(SNAPSHOT_URL, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        log.warning("snapshot_fetch_failed", error=str(e))
        return None


def current_price(snapshot: dict, symbol: str, terms: dict) -> Decimal | None:
    asset_class = terms["asset_class"]

    if asset_class == "BOND":
        curve = (snapshot.get("curves") or {}).get(terms.get("curve", "USD_GOV"))
        if not curve:
            return None
        return Decimal(str(bond_pv(terms, curve)))

    spot = (snapshot.get("spots") or {}).get(symbol)
    if not spot:
        return None

    price = spot.get("mid") or spot.get("spot")
    return Decimal(str(price)) if price is not None else None
