from datetime import date

from market_data_service import curve_store, feeds
from market_data_service.curve_feed import wire_curve


def list_curves(provider=None, include_raw=False):
    if provider is not None and provider not in feeds.WIRED_PROVIDERS:
        return None, f"unknown or unwired provider: {provider}", 404
    curves = curve_store.latest_curve_sets(provider, include_raw)
    return [wire_curve(entry) for entry in curves], None, 200


def snapshot_curves():
    curves, _, _ = list_curves()
    return {entry["curve_name"]: entry for entry in curves}


def get_curve_revision(provider, curve_name, as_of, include_raw=False):
    if provider not in feeds.WIRED_PROVIDERS:
        return None, f"unknown or unwired provider: {provider}", 404
    try:
        as_of_date = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return None, "as_of must be an ISO date", 400
    entry = curve_store.curve_revision(provider, curve_name, as_of_date, include_raw)
    if entry is None:
        return None, f"curve revision not found: {provider} {curve_name} {as_of}", 404
    return wire_curve(entry), None, 200
