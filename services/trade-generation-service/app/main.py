import threading
import time
import urllib.error
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app import book_client, generator
from app.api import app
from app.config import HOST, PORT, SERVICE_NAME
from shared.logging_config import configure_logging, get_logger

log = get_logger(SERVICE_NAME)


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


def _worker():
    while True:
        try:
            generator.set_books(book_client.ensure_books())
            break
        except urllib.error.URLError:
            log.warning("books_not_ready")
            time.sleep(2)
    generator.run_loop()


if __name__ == "__main__":
    configure_logging()
    log.info("starting")
    threading.Thread(target=_worker, daemon=True).start()
    app.run(host=HOST, port=PORT, server=ThreadedServer)
