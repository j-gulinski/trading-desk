from desk_runtime.service_runtime import run_service
from monitoring_service.config import PORT, SERVICE_NAME


def build():
    from monitoring_service.api import app
    from monitoring_service.log_collector import collect_loop
    from monitoring_service.monitor import watchers

    return app, (*watchers(), collect_loop)


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
