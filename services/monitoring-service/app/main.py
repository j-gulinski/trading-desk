from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app.api import app
from app.monitor import start_monitors
from app.config import HOST, PORT, SERVICE_NAME
from shared.logging_config import configure_logging, get_logger


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        start_monitors()
        server.serve_forever()


if __name__ == "__main__":
    configure_logging()
    get_logger(SERVICE_NAME).info("starting")
    app.run(host=HOST, port=PORT, server=ThreadedServer)
