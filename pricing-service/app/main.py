import logging
import threading
from app.api import app
from app.market_data_client import market_data_stream_consumer
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Pricing Service...")
    threading.Thread(target=market_data_stream_consumer, daemon=True).start()
    app.run(host="0.0.0.0", port=8002, server=ThreadedServer)
