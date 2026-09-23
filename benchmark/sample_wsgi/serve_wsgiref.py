# Stage 4B "before": the sample on the server every service ran on until then — desk-runtime's
# ThreadedServer (wsgiref, one thread per connection), copied here because 4B removed it.
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from sample_wsgi.app import app


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


make_server("127.0.0.1", int(sys.argv[1]), app, server_class=ThreadingWSGIServer).serve_forever()
