import logging
import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

from app.api import app
from app.market_data_client import market_data_stream_consumer
from app.valuation_engine import trade_refresh_loop
from app.config import HOST, PORT, LOG_LEVEL, SERVICE_NAME


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO))
    logging.info("Starting %s...", SERVICE_NAME)
    threading.Thread(target=market_data_stream_consumer, daemon=True).start()
    threading.Thread(target=trade_refresh_loop, daemon=True).start()
    app.run(host=HOST, port=PORT, server=ThreadedServer)
