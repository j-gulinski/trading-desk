from books_service.config import PORT, SERVICE_NAME
from desk_runtime.service_runtime import run_service


def build():
    from books_service.api import app

    return app, ()


def main():
    run_service(SERVICE_NAME, PORT, build)


if __name__ == "__main__":
    main()
