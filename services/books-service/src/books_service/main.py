from books_service.api import app
from books_service.config import PORT, SERVICE_NAME
from desk_runtime.service_runtime import run_service

def main():
    run_service(SERVICE_NAME, app, PORT)


if __name__ == "__main__":
    main()
