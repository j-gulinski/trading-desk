import time

from app import cache, repository
from app.config import SERVICE_NAME
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
