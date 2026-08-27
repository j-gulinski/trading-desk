from market_data_service.api import app
from market_data_service.config import PORT, SERVICE_NAME
from market_data_service.curve_store import prune_retired_curve_sets
from market_data_service.retention import retention_sweep_loop
from market_data_service.scheduler import POLL_LOOPS
from desk_runtime.service_runtime import run_service

def main():
    prune_retired_curve_sets()
    run_service(SERVICE_NAME, app, PORT, background=(*POLL_LOOPS, retention_sweep_loop))


if __name__ == "__main__":
    main()
