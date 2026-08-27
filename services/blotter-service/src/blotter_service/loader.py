import time

from blotter_service import cache, repository
from blotter_service.config import ACTIVE_TRADES_REFRESH_SECONDS, SERVICE_NAME
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def reconcile_active_trades():
    with cache.reconciliation_lock:
        fresh = repository.load_active_trades()
        fresh_ids = {trade.trade_id for trade in fresh}
        previous_ids = {trade.trade_id for trade in cache.trades.query()}
        cache.trades.replace_all(fresh)
        for trade_id in previous_ids - fresh_ids:
            cache.drop_valuation(trade_id)
    return fresh


def bootstrap_trades(retries: int = 10, delay: int = 2) -> None:
    for attempt in range(1, retries + 1):
        try:
            trades = reconcile_active_trades()
            log.info("bootstrapped", trades=len(trades))
            return
        except Exception:
            log.warning("bootstrap_retry", attempt=attempt, retries=retries)
            time.sleep(delay)
    log.error("bootstrap_failed")


def active_trades_refresh_loop() -> None:
    while True:
        time.sleep(ACTIVE_TRADES_REFRESH_SECONDS)
        try:
            reconcile_active_trades()
        except Exception:
            log.exception("active_trades_refresh_failed")
