import json
import logging
import urllib.request
import urllib.error
from decimal import Decimal

from shared.pricing_math import bond_pv
from app.config import SNAPSHOT_URL


def fetch_snapshot() -> dict | None:
    try:
        with urllib.request.urlopen(SNAPSHOT_URL, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logging.warning("Failed to fetch market-data snapshot: %s", e)
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
