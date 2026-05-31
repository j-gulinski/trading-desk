import queue
import logging
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter
from app import persistence


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


def publish_valuation(pricing_event):
    with persistence.clients_lock:
        targets = list(persistence.client_event_queues)
    for q in targets:
        try:
            q.put_nowait(pricing_event)
        except queue.Full:
            logging.debug("Dropped tick for slow client")
