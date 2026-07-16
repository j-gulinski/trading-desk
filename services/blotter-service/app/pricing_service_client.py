import time
import json
import urllib.request
import urllib.error

from shared.audit import write_audit
from shared.logging_config import get_logger
from app import service
from app.config import VALUATION_STREAM_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


def valuation_stream_consumer():
    while True:
        log.info("stream_connecting", url=VALUATION_STREAM_URL)
        try:
            request = urllib.request.Request(VALUATION_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                write_audit(SERVICE_NAME, "STREAM_CONNECTED", "Connected to valuation stream")
                for raw in stream:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        valuation = json.loads(line[len("data:"):].strip())
                        service.handle_valuation(valuation)
        except urllib.error.URLError as e:
            log.warning("stream_failed", error=str(e))
        except Exception:
            log.exception("stream_error")
        finally:
            write_audit(SERVICE_NAME, "STREAM_DISCONNECTED", "Valuation stream disconnected", severity="WARNING")
        time.sleep(5)
