import logging
import threading
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter
from app.api import app
from app.monitor import market_data_monitoring_loop, pricing_monitoring_loop


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting Monitoring Service...")
    threading.Thread(target=market_data_monitoring_loop, daemon=True).start()
    threading.Thread(target=pricing_monitoring_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8003, server=ThreadedServer)
