from app.api import app
from app.config import PORT, SERVICE_NAME
from app.curve_store import prune_retired_curve_sets
from app.retention import retention_sweep_loop
from app.scheduler import POLL_LOOPS
from shared.service_runtime import run_service

if __name__ == "__main__":
    prune_retired_curve_sets()
    run_service(SERVICE_NAME, app, PORT, background=(*POLL_LOOPS, retention_sweep_loop))
