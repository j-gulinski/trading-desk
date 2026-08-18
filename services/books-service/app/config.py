from shared.config import env_str

SERVICE_NAME = "books-service"
PORT = 8004

BLOTTER_SERVICE_URL = env_str("BLOTTER_SERVICE_URL")
BLOTTER_TRADES_URL = f"{BLOTTER_SERVICE_URL}/trades" if BLOTTER_SERVICE_URL else None
