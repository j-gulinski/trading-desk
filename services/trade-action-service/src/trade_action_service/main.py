from trade_action_service.api import app
from trade_action_service.config import PORT, SERVICE_NAME
from trade_action_service.trade_processor import worker_loop
from desk_runtime.service_runtime import run_service

def main():
    run_service(SERVICE_NAME, app, PORT, background=[worker_loop])


if __name__ == "__main__":
    main()
