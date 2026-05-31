import threading
import queue
import logging
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
from bottle import ServerAdapter

clients_lock = threading.Lock()
client_event_queues = set()


class ThreadedServer(ServerAdapter):
    def run(self, handler):
        class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        server.serve_forever()


def publish_tick(tick):
    with clients_lock:
        targets = list(client_event_queues)
    for q in targets:
        try:
            q.put_nowait(tick)
        except queue.Full:
            logging.debug("Dropped tick for slow client")
