from desk_runtime.config import env_str

SERVICE_NAME = "blotter-service"
PORT = 8006

ACTIVE_TRADES_REFRESH_SECONDS = 5

VALUATION_STREAM_URL = env_str("VALUATION_STREAM_URL")
