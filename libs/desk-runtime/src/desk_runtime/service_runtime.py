import threading

from gunicorn.app.base import BaseApplication

from desk_runtime.config import SERVER_THREADS
from desk_runtime.http import install_json_errors, json_response
from desk_runtime.logging_config import configure_logging, get_logger


def install_default_health(app, service_name):
    if all(route.rule != "/health" for route in app.routes):
        app.route("/health")(
            lambda: json_response({"service": service_name, "status": "UP"})
        )


class ServiceApplication(BaseApplication):
    def __init__(self, service_name, port, build):
        self.service_name = service_name
        self.port = port
        self.build = build
        super().__init__()

    def load_config(self):
        self.cfg.set("bind", f"0.0.0.0:{self.port}")
        self.cfg.set("workers", 1)
        self.cfg.set("worker_class", "gthread")
        self.cfg.set("threads", SERVER_THREADS)
        self.cfg.set("graceful_timeout", 5)

    def load(self):
        configure_logging(self.service_name)
        get_logger(self.service_name).info("starting")
        app, background = self.build()
        install_default_health(app, self.service_name)
        install_json_errors(app)
        for target in background:
            threading.Thread(target=target, daemon=True).start()
        return app


def run_service(service_name, port, build):
    ServiceApplication(service_name, port, build).run()
