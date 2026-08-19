import time

from app import cache, repository
from app.config import ACTIVE_TRADES_REFRESH_SECONDS, SERVICE_NAME
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def bootstrap_trades(retries: int = 10, delay: int = 2) -> None:
    for attempt in range(1, retries + 1):
        try:
            trades = repository.load_active_trades()
            cache.trades.add_many(trades)
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
            fresh = repository.load_active_trades()
            fresh_ids = {trade.trade_id for trade in fresh}
            cache.trades.add_many(fresh)
            # drop trades that left ACTIVE, and their cached valuations
            for trade in cache.trades.query():
                if trade.trade_id not in fresh_ids:
                    cache.trades.remove(trade.trade_id)
                    cache.drop_valuation(trade.trade_id)
        except Exception:
            log.exception("active_trades_refresh_failed")
