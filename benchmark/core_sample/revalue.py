import json
import random
import time

from core_sample.core import CURVE, OPTION
from desk_pricing.european_option import black_scholes

POSITIONS = 1_000_000

spots = [100.0 * random.uniform(0.8, 1.2) for _ in range(POSITIONS)]
started = time.process_time()
for spot in spots:
    black_scholes(OPTION, spot, CURVE)
seconds = time.process_time() - started

micros = seconds / POSITIONS * 1e6
print(json.dumps({
    "model": "Black-Scholes, desk_pricing.european_option.black_scholes",
    "positions": POSITIONS,
    "us_per_position": round(micros, 3),
    "cores_for_1m_positions_per_minute": round(seconds / 60, 4),
}))
