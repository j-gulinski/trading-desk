import time
import logging
import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app.api import app
from app import persistence
from app.generator import start_generators
from app.config import HOST, PORT, LOG_LEVEL, SERVICE_NAME, SNAPSHOT_INTERVAL_SECONDS


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
    logging.basicConfig(level=getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO))
    logging.info("Starting %s...", SERVICE_NAME)
    start_generators()
    threading.Thread(target=snapshot_writer, daemon=True).start()
    app.run(host=HOST, port=PORT, server=ThreadedServer)
