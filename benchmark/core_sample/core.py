import math
import random
import threading
import time

from desk_pricing.european_option import black_scholes
from desk_runtime.logging_config import configure_logging

PROVIDER_URL = "http://stub-core:9000/delay/200"
PROVIDER_TIMEOUT_SECONDS = 5
INSTRUMENTS = 10_000
BOOKS = 100
IN_FLIGHT = 1_250
UPDATES_PER_SECOND = 50
TICK_SECONDS = 0.01
CURVE = {"tenors": [0.25, 1.0, 5.0], "rates": [0.03, 0.032, 0.035]}
OPTION = {"strike": 100.0, "maturity_years": 0.5, "volatility": 0.25, "option_type": "CALL"}

INSERT_ORDER = "INSERT INTO orders (instrument, book, quantity) VALUES (:instrument, :book, :quantity)"
UPDATE_POSITION = (
    "UPDATE positions SET quantity = quantity + :quantity, updated_at = now()"
    " WHERE instrument = :instrument AND book = :book RETURNING quantity"
)

configure_logging()


def known_position(instrument, book):
    return 0 <= instrument < INSTRUMENTS and 0 <= book < BOOKS


def new_order(instrument, book):
    return {"instrument": instrument, "book": book, "quantity": random.randint(1, 100)}


def order_result(order, position):
    return {**order, "position": position}


def valuation_update():
    spot = 100.0 * math.exp(random.gauss(0.0, 0.01))
    return {
        "instrument": random.randrange(INSTRUMENTS),
        "book": random.randrange(BOOKS),
        "value": round(black_scholes(OPTION, spot, CURVE)["price"], 4),
        "published_at": time.time(),
    }


class Ingest:
    """Refresh schedule and counters for every instrument."""

    def __init__(self, period):
        self.period = period
        self.start = time.monotonic()
        self.slot = period / INSTRUMENTS
        self.received = [self.start] * INSTRUMENTS
        self.counts = {"due": 0, "completed": 0, "missed": 0, "errors": 0}
        self.age_p95 = []
        self.lock = threading.Lock()
        self.last_tick = 0.0

    def tick(self):
        now = time.monotonic() - self.start
        first, last = math.ceil(self.last_tick / self.slot), math.ceil(now / self.slot)
        if int(now) > int(self.last_tick):
            self.sample_age(now)
        self.last_tick = now
        self.count("due", last - first)
        return [(n % INSTRUMENTS, self.start + n * self.slot) for n in range(first, last)]

    def is_late(self, due):
        late = time.monotonic() >= due + self.period
        if late:
            self.count("missed")
        return late

    def stored(self, instrument):
        self.received[instrument] = time.monotonic()
        self.count("completed")

    def count(self, name, amount=1):
        with self.lock:
            self.counts[name] += amount

    def sample_age(self, now):
        ages = sorted(time.monotonic() - received for received in self.received)
        self.age_p95.append([round(now, 1), round(ages[int(0.95 * len(ages))], 3)])

    def stats(self):
        with self.lock:
            counts = dict(self.counts)
        elapsed = round(time.monotonic() - self.start, 1)
        return {"period": self.period, "elapsed": elapsed, **counts, "age_p95": self.age_p95}
