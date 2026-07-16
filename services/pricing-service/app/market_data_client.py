import time
import json
import urllib.request
import urllib.error

from shared.audit import write_audit
from shared.logging_config import get_logger
from app import cache
from app.config import MARKET_DATA_STREAM_URL, SERVICE_NAME
from app.valuation_engine import value_symbol, value_curve
from app.valuation_publisher import publish_valuation

log = get_logger(SERVICE_NAME)
market_data_connection = "DISCONNECTED"

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
        log.info("stream_connecting", url=MARKET_DATA_STREAM_URL)
        try:
            request = urllib.request.Request(MARKET_DATA_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                with cache.data_lock:
                    cache.market_data_connection = "CONNECTED"
                write_audit(SERVICE_NAME, "STREAM_CONNECTED", "Connected to market data stream")
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
            log.warning("stream_failed", error=str(e))
        except Exception:
            log.exception("stream_error")
        finally:
            with cache.data_lock:
                cache.market_data_connection = "RECONNECTING"
            write_audit(SERVICE_NAME, "STREAM_DISCONNECTED", "Market data stream disconnected", severity="WARNING")
        time.sleep(5)
