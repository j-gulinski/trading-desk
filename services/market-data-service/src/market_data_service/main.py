from desk_runtime.service_runtime import run_service
from market_data_service.config import PORT, SERVICE_NAME


def build():
    from market_data_service.api import app
    from market_data_service.curve_store import prune_retired_curve_sets
    from market_data_service.feeds import POLL_LOOPS
    from market_data_service.quote_board import retention_loop

    prune_retired_curve_sets()
    return app, (*POLL_LOOPS, retention_loop)


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
