import time
import json
import logging
import urllib.request
import urllib.error

from app import service
from app.config import VALUATION_STREAM_URL


def valuation_stream_consumer():
    while True:
        logging.info("Connecting to valuation stream at %s ...", VALUATION_STREAM_URL)
        try:
            request = urllib.request.Request(VALUATION_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                logging.info("Connected to valuation stream")
                for raw in stream:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        valuation = json.loads(line[len("data:"):].strip())
                        service.handle_valuation(valuation)
        except urllib.error.URLError as e:
            logging.warning("Valuation stream connection failed: %s. Reconnecting in 5s...", e)
        except Exception:
            logging.exception("Unexpected valuation stream error. Reconnecting in 5s...")
        time.sleep(5)
