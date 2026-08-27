from monitoring_service.api import app
from monitoring_service.config import PORT, SERVICE_NAME
from monitoring_service.log_collector import start_collector
from monitoring_service.monitor import start_monitors
from desk_runtime.service_runtime import run_service

def main():
    run_service(SERVICE_NAME, app, PORT, startup=[start_monitors, start_collector])


if __name__ == "__main__":
    main()
