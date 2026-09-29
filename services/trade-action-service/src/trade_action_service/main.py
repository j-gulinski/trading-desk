from desk_runtime.service_runtime import run_service
from trade_action_service.config import PORT, SERVICE_NAME


def build():
    from trade_action_service.api import app

    return app, ()


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
