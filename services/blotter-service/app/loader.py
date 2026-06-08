import time
import logging

from app import cache, repository


def bootstrap_trades(retries: int = 10, delay: int = 2) -> None:
    for attempt in range(1, retries + 1):
        try:
            trades = repository.load_active_trades()
            cache.trades.add_many(trades)
            logging.info("Bootstrapped %d active trades from DB", len(trades))
            return
        except Exception:
            logging.warning(
                "Trade bootstrap attempt %d/%d failed; retrying in %ss", attempt, retries, delay
            )
            time.sleep(delay)
    logging.error("Trade bootstrap failed; relying on stream lazy-load")
