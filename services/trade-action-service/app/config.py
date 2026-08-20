from shared.config import env_float
from shared.providers import FINNHUB, TWELVE_DATA

SERVICE_NAME = "trade-action-service"
PORT = 8008

QUOTE_PROVIDER_CHOICES = (FINNHUB, TWELVE_DATA)

TRADE_PRICE_TOLERANCE_PCT = env_float("TRADE_PRICE_TOLERANCE_PCT", 1.0)
