from app.api import app
from app.config import PORT, SERVICE_NAME
from app.market_data_client import market_data_stream_consumer
from app.valuation_engine import restore_terminal_valuations, trade_refresh_loop
from shared.service_runtime import run_service

if __name__ == "__main__":
    run_service(
        SERVICE_NAME,
        app,
        PORT,
        startup=[restore_terminal_valuations],
        background=[market_data_stream_consumer, trade_refresh_loop],
    )
