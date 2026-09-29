from desk_runtime.service_runtime import run_service
from pricing_service.config import PORT, SERVICE_NAME


def build():
    from pricing_service.api import app
    from pricing_service.market_data_client import market_data_stream_consumer
    from pricing_service.valuation_engine import restore_terminal_valuations, trade_refresh_loop

    restore_terminal_valuations()
    return app, (market_data_stream_consumer, trade_refresh_loop)


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
