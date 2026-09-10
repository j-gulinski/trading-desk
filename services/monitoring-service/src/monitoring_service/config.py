from desk_runtime.config import SERVICE_PORTS, SERVICE_URLS
from desk_runtime.config import LOG_DIR

SERVICE_NAME = "monitoring-service"
PORT = SERVICE_PORTS[SERVICE_NAME]

POLL_INTERVAL_SECONDS = 5

LOG_SCAN_INTERVAL_SECONDS = 1.0
LOG_BUFFER_LINES = 10_000
LOG_MINUTE_BUCKETS = 15
LOG_WARM_START_TAIL_BYTES = 64_000

TARGETS = {name: url + "/health" for name, url in SERVICE_URLS.items()}
