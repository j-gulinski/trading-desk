from blotter_service.config import PORT, SERVICE_NAME
from desk_runtime.service_runtime import run_service


def build():
    from blotter_service.api import app
    from blotter_service.pricing_service_client import valuation_stream_consumer

    return app, (valuation_stream_consumer,)


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
