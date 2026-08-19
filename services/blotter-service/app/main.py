from app.api import app
from app.config import PORT, SERVICE_NAME
from app.loader import active_trades_refresh_loop, bootstrap_trades
from app.pricing_service_client import valuation_stream_consumer
from shared.service_runtime import run_service

if __name__ == "__main__":
    run_service(SERVICE_NAME, app, PORT, startup=[bootstrap_trades],
                background=[valuation_stream_consumer, active_trades_refresh_loop])
