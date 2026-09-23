# Stage 4B "after": the sample on the server desk-runtime now runs every service on.
import sys

from desk_runtime.service_runtime import ServiceServer
from sample_wsgi.app import app

ServiceServer(app, int(sys.argv[1])).run()
