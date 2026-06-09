import time
import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app.api import app
from app import persistence
from app.generator import start_generators
from app.config import HOST, PORT, SERVICE_NAME, SNAPSHOT_INTERVAL_SECONDS
from shared.logging_config import configure_logging, get_logger


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()

def snapshot_writer():
    while True:
        time.sleep(SNAPSHOT_INTERVAL_SECONDS)
        persistence.save_snapshot()

if __name__ == "__main__":
    configure_logging()
    get_logger(SERVICE_NAME).info("starting")
    start_generators()
    threading.Thread(target=snapshot_writer, daemon=True).start()
    app.run(host=HOST, port=PORT, server=ThreadedServer)
