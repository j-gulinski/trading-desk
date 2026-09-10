from desk_runtime.config import SERVICE_PORTS, SERVICE_URLS

SERVICE_NAME = "blotter-service"
PORT = SERVICE_PORTS[SERVICE_NAME]

ACTIVE_TRADES_REFRESH_SECONDS = 5

VALUATION_STREAM_URL = SERVICE_URLS["pricing-service"] + "/valuation-stream"
VALUATION_SNAPSHOT_URL = SERVICE_URLS["pricing-service"] + "/valuations"
