import importlib
import sys
import threading

from desk_runtime.config import SERVICE_PORTS, env_str
from desk_runtime.http import install_json_errors
from desk_runtime.logging_config import configure_logging, get_logger
from desk_runtime.service_runtime import install_default_health

VARIANTS = ("wsgiref", "gunicorn", "fastapi")
ASYNC_STREAM_SERVICES = ("market-data-service", "pricing-service")


def run_wsgiref(name, service):
    from sample_wsgi.wsgiref_server import ThreadedServer

    configure_logging(name)
    get_logger(name).info("starting")
    app, background = service.build()
    install_default_health(app, name)
    install_json_errors(app)
    for target in background:
        threading.Thread(target=target, daemon=True).start()
    app.run(host="0.0.0.0", port=SERVICE_PORTS[name], server=ThreadedServer, quiet=True)


def main(name):
    variant = env_str("VARIANT", "gunicorn")
    if name not in SERVICE_PORTS or variant not in VARIANTS:
        raise SystemExit(f"unknown service {name} or VARIANT {variant}")
    service = importlib.import_module(f"{name.replace('-', '_')}.main")
    if variant == "wsgiref":
        run_wsgiref(name, service)
    elif variant == "fastapi" and name in ASYNC_STREAM_SERVICES:
        from desk_day.fastapi_streams import run

        run(name)
    else:
        service.main()


if __name__ == "__main__":
    main(sys.argv[1])
