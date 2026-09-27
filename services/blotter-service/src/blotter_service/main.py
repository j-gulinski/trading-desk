from blotter_service.api import app
from blotter_service.config import PORT, SERVICE_NAME
from blotter_service.pricing_service_client import valuation_stream_consumer
from desk_runtime.service_runtime import run_service


def main():
    run_service(SERVICE_NAME, app, PORT, background=[valuation_stream_consumer])


if __name__ == "__main__":
    main()
