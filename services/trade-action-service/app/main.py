from app.api import app
from app.config import PORT, SERVICE_NAME
from app.trade_processor import worker_loop
from shared.service_runtime import run_service

if __name__ == "__main__":
    run_service(SERVICE_NAME, app, PORT, background=[worker_loop])
