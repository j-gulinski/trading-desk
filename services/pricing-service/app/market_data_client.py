import time
import json
import logging
import urllib.request
import urllib.error

from app import cache
from app.config import MARKET_DATA_STREAM_URL
from app.valuation_engine import value_symbol, value_curve
from app.valuation_publisher import publish_valuation


def _handle(event_type, tick):
    with cache.data_lock:
        cache.ticks_received += 1
        cache.last_event_timestamp = tick.get("event_time")

    if event_type == "curve_tick":
        cache.update_curve(tick)
        for event in value_curve(tick["curve_name"]):
            publish_valuation(event)
        return

    cache.update_spot(tick)
    for event in value_symbol(tick["symbol"]):
        publish_valuation(event)


def market_data_stream_consumer():
    while True:
        logging.info("Connecting to market data stream at %s ...", MARKET_DATA_STREAM_URL)
        try:
            request = urllib.request.Request(MARKET_DATA_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                with cache.data_lock:
                    cache.market_data_connection = "CONNECTED"
                event_type = None
                for raw in stream:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        tick = json.loads(line[len("data:"):].strip())
                        _handle(event_type, tick)
        except urllib.error.URLError as e:
            logging.warning("Stream connection failed: %s. Reconnecting in 5s...", e)
        except Exception:
            logging.exception("Unexpected stream error. Reconnecting in 5s...")
        finally:
            with cache.data_lock:
                cache.market_data_connection = "RECONNECTING"
        time.sleep(5)
