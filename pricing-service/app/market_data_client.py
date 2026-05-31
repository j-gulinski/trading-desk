import time
import json
import logging
import urllib.request
import urllib.error
from app import persistence
from app.config import STREAM_URL
from app.valuation_engine import update_pricing
from app.valuation_publisher import publish_valuation


def market_data_stream_consumer():
    while True:
        logging.info(f"Connecting to Market Data Stream at {STREAM_URL}...")
        try:
            request = urllib.request.Request(STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                with persistence.data_lock:
                    persistence.market_data_connection = "CONNECTED"
                for line in stream:
                    decoded_line = line.decode("utf-8").strip()
                    if not decoded_line:
                        continue
                    logging.debug(f"Received tick from stream: {decoded_line}")
                    if decoded_line.startswith("data: "):
                        raw_json = decoded_line[6:]
                        tick = json.loads(raw_json)

                        with persistence.data_lock:
                            persistence.ticks_received += 1
                            persistence.last_event_timestamp = tick["timestamp"]
                            pricing_event = update_pricing(tick)

                        if pricing_event:
                            publish_valuation(pricing_event)

        except urllib.error.URLError as e:
            logging.error(f"Stream connection failed: {e}. Retrying in 5 seconds...")
        except Exception as e:
            logging.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
        finally:
            with persistence.data_lock:
                persistence.market_data_connection = "DISCONNECTED"
        with persistence.data_lock:
            persistence.market_data_connection = "RECONNECTING"
        time.sleep(5)
