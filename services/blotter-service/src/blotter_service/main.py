from blotter_service.api import app
from blotter_service.config import PORT, SERVICE_NAME
from blotter_service.loader import active_trades_refresh_loop, bootstrap_trades
from blotter_service.pricing_service_client import valuation_stream_consumer
from desk_runtime.service_runtime import run_service

def main():
    run_service(SERVICE_NAME, app, PORT, startup=[bootstrap_trades],
                background=[valuation_stream_consumer, active_trades_refresh_loop])


if __name__ == "__main__":
    main()
