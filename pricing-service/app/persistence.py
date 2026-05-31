import threading
import queue
from shared import INSTRUMENTS

data_lock = threading.Lock()
clients_lock = threading.Lock()

market_data_connection = "DISCONNECTED"
ticks_received = 0
last_event_timestamp = None
client_event_queues = set()

market_state = {data["instrument_id"]: data.copy() for key, data in INSTRUMENTS.items()}
