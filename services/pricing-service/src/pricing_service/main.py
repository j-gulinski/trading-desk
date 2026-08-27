from pricing_service.api import app
from pricing_service.config import PORT, SERVICE_NAME
from pricing_service.market_data_client import market_data_stream_consumer
from pricing_service.valuation_engine import restore_terminal_valuations, trade_refresh_loop
from desk_runtime.service_runtime import run_service

def main():
    run_service(
        SERVICE_NAME,
        app,
        PORT,
        startup=[restore_terminal_valuations],
        background=[market_data_stream_consumer, trade_refresh_loop],
    )


if __name__ == "__main__":
    main()
