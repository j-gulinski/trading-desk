from desk_runtime.config import LOG_DIR, env_str

SERVICE_NAME = "monitoring-service"
PORT = 8003

POLL_INTERVAL_SECONDS = 5

LOG_SCAN_INTERVAL_SECONDS = 1.0
LOG_BUFFER_LINES = 10_000
LOG_MINUTE_BUCKETS = 15
LOG_WARM_START_TAIL_BYTES = 64_000

TARGETS = {
    name: url
    for name, url in {
        "monitoring-service": env_str("MONITORING_SERVICE_HEALTHCHECK_URL"),
        "market-data-service": env_str("MARKET_DATA_SERVICE_HEALTHCHECK_URL"),
        "pricing-service": env_str("PRICING_SERVICE_HEALTHCHECK_URL"),
        "books-service": env_str("BOOKS_SERVICE_HEALTHCHECK_URL"),
        "trade-action-service": env_str("TRADE_ACTION_SERVICE_HEALTHCHECK_URL"),
        "blotter-service": env_str("BLOTTER_SERVICE_HEALTHCHECK_URL"),
    }.items()
    if url
}
