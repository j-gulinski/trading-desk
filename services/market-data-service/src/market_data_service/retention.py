import time
from datetime import timedelta

from market_data_service import official_fixing_set, quote_lifecycle, quote_store
from market_data_service.config import (
    RETENTION_SWEEP_INTERVAL_SECONDS,
    SERVICE_NAME,
    SNAPSHOT_RETENTION_DAYS,
)
from market_data_service.publisher import publish_removal
from desk_domain.active_set import load_active_set
from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from desk_domain.models import MarketDataSnapshot, MarketDataSpotPrice, Trade

log = get_logger(SERVICE_NAME)


def _is_board_stray(provider, symbol, official_fixings, active):
    if provider in official_fixings:
        return symbol not in official_fixings[provider]
    entry = active.get(symbol)
    return entry is None or not entry.serves(provider)


def sweep_snapshots():
    cutoff = utcnow() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    with session_scope() as session:
        by_trades = session.query(Trade.entry_snapshot_id).filter(
            Trade.entry_snapshot_id.isnot(None)
        )
        by_closes = session.query(Trade.close_snapshot_id).filter(
            Trade.close_snapshot_id.isnot(None)
        )
        by_board = session.query(MarketDataSpotPrice.latest_snapshot_id).filter(
            MarketDataSpotPrice.latest_snapshot_id.isnot(None)
        )
        deleted = (
            session.query(MarketDataSnapshot)
            .filter(
                MarketDataSnapshot.received_at < cutoff,
                ~MarketDataSnapshot.snapshot_id.in_(by_trades),
                ~MarketDataSnapshot.snapshot_id.in_(by_closes),
                ~MarketDataSnapshot.snapshot_id.in_(by_board),
            )
            .delete(synchronize_session=False)
        )
    log.info(
        "snapshot_retention_swept", deleted=deleted,
        retention_days=SNAPSHOT_RETENTION_DAYS,
    )
    return deleted


def sweep_board_strays():
    active = load_active_set()
    official_fixings = official_fixing_set.official_fixing_board_symbols()
    with session_scope() as session:
        rows = session.query(
            MarketDataSpotPrice.provider,
            MarketDataSpotPrice.symbol,
        ).all()
        candidates = [
            (provider, symbol)
            for provider, symbol in rows
            if _is_board_stray(provider, symbol, official_fixings, active)
        ]
    deleted = 0
    for provider, symbol in candidates:
        with quote_lifecycle.locked_keys(symbol, (provider,)):
            current_fixings = official_fixing_set.official_fixing_board_symbols()
            current_active = load_active_set()
            if not _is_board_stray(
                provider, symbol, current_fixings, current_active
            ):
                continue
            removed = quote_store.delete_board_rows(symbol, (provider,))
            if not removed:
                continue
            deleted += removed
            publish_removal([{"provider": provider, "symbol": symbol}])
    if deleted:
        log.info("board_strays_swept", rows=deleted)
    return deleted


def retention_sweep_loop():
    while True:
        for sweep in (sweep_snapshots, sweep_board_strays):
            try:
                sweep()
            except Exception:
                log.exception("retention_sweep_failed", sweep=sweep.__name__)
        time.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
