import os
from shared import INSTRUMENTS, get_iso_timestamp

TIME_INTERVAL_MS = int(os.getenv("TIME_INTERVAL_MS", 100))
