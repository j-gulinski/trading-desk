from desk_runtime.config import SERVICE_PORTS
from desk_runtime.config import env_float

SERVICE_NAME = "trade-action-service"
PORT = SERVICE_PORTS[SERVICE_NAME]

TRADE_PRICE_TOLERANCE_PCT = env_float("TRADE_PRICE_TOLERANCE_PCT", 1.0)
