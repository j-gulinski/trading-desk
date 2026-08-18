import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from bottle import ServerAdapter

from shared.logging_config import configure_logging, get_logger


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


def install_default_health(app, service_name):
    if all(route.rule != "/health" for route in app.routes):
        app.route("/health")(lambda: {"service": service_name, "status": "UP"})


def run_service(service_name, app, port, startup=(), background=()):
    configure_logging(service_name)
    get_logger(service_name).info("starting")
    install_default_health(app, service_name)
    for hook in startup:
        hook()
    for target in background:
        threading.Thread(target=target, daemon=True).start()
    app.run(host="0.0.0.0", port=port, server=ThreadedServer)
