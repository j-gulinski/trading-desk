import random
import time
import logging
from app import persistence
from app.config import TIME_INTERVAL_MS
from app.publisher import publish_tick
from shared import get_iso_timestamp


def generate_equity_tick(timestamp):
    current_equity_mid = (persistence.snapshot["EQ_ACME"]["bid"] + persistence.snapshot["EQ_ACME"]["ask"]) / 2
    new_equity_mid = max(1.0, current_equity_mid + random.uniform(-0.2, 0.2))
    equity_tick = {
        "event_id": persistence.ticks_generated,
        "timestamp": timestamp,
        "instrument_id": persistence.snapshot["EQ_ACME"]["instrument_id"],
        "asset_type": persistence.snapshot["EQ_ACME"]["asset_type"],
        "market_symbol": persistence.snapshot["EQ_ACME"]["market_symbol"],
        "bid": round(new_equity_mid - 0.05, 4),
        "ask": round(new_equity_mid + 0.05, 4),
        "last": round(new_equity_mid + random.uniform(-0.02, 0.02), 4),
    }
    persistence.snapshot["EQ_ACME"].update({
        "bid": equity_tick["bid"],
        "ask": equity_tick["ask"],
        "last": equity_tick["last"],
    })
    return equity_tick


def generate_bond_tick(timestamp):
    current_bond_yield = persistence.snapshot["BOND_GOVT_5Y"]["yield"]
    new_bond_yield = max(0.03, min(0.06, current_bond_yield + random.uniform(-0.003, 0.003)))
    bond_tick = {
        "event_id": persistence.ticks_generated,
        "timestamp": timestamp,
        "instrument_id": persistence.snapshot["BOND_GOVT_5Y"]["instrument_id"],
        "asset_type": persistence.snapshot["BOND_GOVT_5Y"]["asset_type"],
        "market_symbol": persistence.snapshot["BOND_GOVT_5Y"]["market_symbol"],
        "yield": round(new_bond_yield, 4),
    }
    persistence.snapshot["BOND_GOVT_5Y"].update({"yield": bond_tick["yield"]})
    return bond_tick


def generate_fx_forward_tick(timestamp):
    current_spot = persistence.snapshot["FX_EURUSD_1Y"]["spot"]
    new_spot = max(1.10, min(1.20, current_spot + random.uniform(-0.01, 0.01)))
    fx_forward_tick = {
        "event_id": persistence.ticks_generated,
        "timestamp": timestamp,
        "instrument_id": persistence.snapshot["FX_EURUSD_1Y"]["instrument_id"],
        "asset_type": persistence.snapshot["FX_EURUSD_1Y"]["asset_type"],
        "market_symbol": persistence.snapshot["FX_EURUSD_1Y"]["market_symbol"],
        "spot": round(new_spot, 4),
        "domestic_rate": persistence.snapshot["FX_EURUSD_1Y"]["domestic_rate"],
        "foreign_rate": persistence.snapshot["FX_EURUSD_1Y"]["foreign_rate"],
    }
    persistence.snapshot["FX_EURUSD_1Y"].update({"spot": fx_forward_tick["spot"]})
    return fx_forward_tick


def market_data_generator():
    while True:
        now = get_iso_timestamp()

        with persistence.data_lock:
            tick_type = random.choice(["EQUITY", "BOND", "FX_FORWARD"])
            if tick_type == "EQUITY":
                tick = generate_equity_tick(now)
            elif tick_type == "BOND":
                tick = generate_bond_tick(now)
            elif tick_type == "FX_FORWARD":
                tick = generate_fx_forward_tick(now)

            persistence.ticks_generated += 1
            persistence.last_event_timestamp = now
            logging.debug(f"Total ticks generated: {persistence.ticks_generated}")

        publish_tick(tick)

        logging.debug(f"Total ticks generated: {persistence.ticks_generated}")
        time.sleep(TIME_INTERVAL_MS / 1000.0)
