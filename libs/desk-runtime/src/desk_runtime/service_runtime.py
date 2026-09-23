import threading

from gunicorn.app.base import BaseApplication

from desk_runtime.config import HTTP_THREADS
from desk_runtime.http import install_json_errors, json_response
from desk_runtime.logging_config import configure_logging, get_logger


class ServiceServer(BaseApplication):
    """gunicorn with one worker process and a pool of HTTP_THREADS threads.

    One process only: services keep live state in memory, and a second copy would split it.
    Startup hooks and background threads run inside the worker, next to the handlers that
    read their state; anything started before the fork would stay in the master.
    """

    def __init__(self, app, port, startup=(), background=()):
        self.app, self.port = app, port
        self.startup, self.background = startup, background
        super().__init__()

    def load_config(self):
        self.cfg.set("bind", f"0.0.0.0:{self.port}")
        self.cfg.set("workers", 1)
        self.cfg.set("threads", HTTP_THREADS)
        # Startup hooks run before the worker's first heartbeat; blotter's retries take ~20 s.
        self.cfg.set("timeout", 120)
        # SSE responses never finish; stop within Docker's 10 s grace period anyway.
        self.cfg.set("graceful_timeout", 5)
        self.cfg.set("post_worker_init", self._start_worker)

    def load(self):
        return self.app

    def _start_worker(self, worker):
        for hook in self.startup:
            hook()
        for target in self.background:
            threading.Thread(target=target, daemon=True).start()


def install_default_health(app, service_name):
    if all(route.rule != "/health" for route in app.routes):
        app.route("/health")(
            lambda: json_response({"service": service_name, "status": "UP"})
        )


def run_service(service_name, app, port, startup=(), background=()):
    configure_logging(service_name)
    get_logger(service_name).info("starting")
    install_default_health(app, service_name)
    install_json_errors(app)
    ServiceServer(app, port, startup, background).run()
