from market_data_service.api import app
from market_data_service.config import PORT, SERVICE_NAME
from market_data_service.curve_store import prune_retired_curve_sets
from market_data_service.feeds import POLL_LOOPS
from market_data_service.quote_board import retention_loop
from desk_runtime.service_runtime import run_service


def main():
    prune_retired_curve_sets()
    run_service(SERVICE_NAME, app, PORT, background=(*POLL_LOOPS, retention_loop))


if __name__ == "__main__":
    main()
