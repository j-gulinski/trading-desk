import threading
import queue as queue_module
from app.config import INSTRUMENTS

data_lock = threading.Lock()
ticks_generated = 0
last_event_timestamp = None
ticks_kept = 100

snapshot = {}
queues = {}

for inst in INSTRUMENTS.values():
    data = {
        "asset_type": inst["type"],
        "instrument_id": inst["instrument_id"],
        "market_symbol": inst["market_symbol"],
    }
    if inst["type"] == "BOND":
        data.update({
            "face_value": inst["face_value"],
            "coupon_rate": inst["coupon_rate"],
            "maturity_years": inst["maturity_years"],
            "payments_per_year": inst["payments_per_year"],
        })
    elif inst["type"] == "FX_FORWARD":
        data["tenor_years"] = inst["tenor_years"]
    snapshot[inst["instrument_id"]] = data
    queues[inst["market_symbol"]] = queue_module.Queue()

snapshot["EQ_ACME"].update({"bid": 99.95, "ask": 100.05, "last": 100.00})
snapshot["BOND_GOVT_5Y"].update({"yield": 0.05})
snapshot["FX_EURUSD_1Y"].update({"spot": 1.16, "domestic_rate": 0.0375, "foreign_rate": 0.0215})
