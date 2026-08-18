from app.api import app
from app.config import PORT, SERVICE_NAME
from app.log_collector import start_collector
from app.monitor import start_monitors
from shared.service_runtime import run_service

if __name__ == "__main__":
    run_service(SERVICE_NAME, app, PORT, startup=[start_monitors, start_collector])
