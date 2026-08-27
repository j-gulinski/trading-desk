from datetime import date

from app import curve_store, scheduler
from app.config import SERVICE_NAME
from app.curve_feed import wire_curve
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def list_curves(provider=None, include_raw=False):
    if provider is not None and provider not in scheduler.wired_providers():
        return None, f"unknown or unwired provider: {provider}", 404
    curves = curve_store.latest_curve_sets(
        provider=provider,
        include_raw=include_raw,
    )
    return [wire_curve(entry) for entry in curves], None, 200


def snapshot_curves():
    curves, _, _ = list_curves()
    return {entry["curve_name"]: entry for entry in curves}


def get_curve_revision(provider, curve_name, as_of, include_raw=False):
    if provider not in scheduler.wired_providers():
        return None, f"unknown or unwired provider: {provider}", 404
    try:
        as_of_date = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return None, "as_of must be an ISO date", 400
    entry = curve_store.curve_revision(
        provider,
        curve_name,
        as_of_date,
        include_raw=include_raw,
    )
    if entry is None:
        return None, f"curve revision not found: {provider} {curve_name} {as_of}", 404
    return wire_curve(entry), None, 200


def refresh(curve=None, provider=None):
    if curve is not None:
        entry, error, status = scheduler.refresh_curve(curve, provider)
        if error is not None:
            log.warning(
                "manual_curve_refresh_rejected",
                curve=curve,
                provider=provider,
                reason=error,
            )
            return None, error, status
        log.info("manual_curve_refresh", curve=curve, provider=provider)
        return wire_curve(entry), None, status
    refreshed, skipped = scheduler.refresh_curves(provider)
    log.info(
        "manual_curve_refresh_all",
        provider=provider,
        refreshed=len(refreshed),
        skipped=skipped,
    )
    return {"refreshed": refreshed, "skipped": skipped}, None, 200
