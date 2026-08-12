import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app.api import app
from app.market_data_client import market_data_stream_consumer
from app.valuation_engine import trade_refresh_loop
from app.config import HOST, PORT, SERVICE_NAME
from shared.logging_config import configure_logging, get_logger


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


if __name__ == "__main__":
    configure_logging(SERVICE_NAME)
    get_logger(SERVICE_NAME).info("starting")
    threading.Thread(target=market_data_stream_consumer, daemon=True).start()
    threading.Thread(target=trade_refresh_loop, daemon=True).start()
    app.run(host=HOST, port=PORT, server=ThreadedServer)
