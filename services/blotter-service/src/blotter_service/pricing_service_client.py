import time
import json
import urllib.request
import urllib.error

from desk_domain.audit import write_audit
from desk_runtime.logging_config import get_logger
from blotter_service import service
from blotter_service.config import VALUATION_STREAM_URL, SERVICE_NAME

log = get_logger(SERVICE_NAME)


def _snapshot_url():
    return VALUATION_STREAM_URL.rsplit("/", 1)[0] + "/valuations"


def _reconcile_valuations():
    try:
        with urllib.request.urlopen(_snapshot_url(), timeout=10) as response:
            rows = json.loads(response.read())
        if not isinstance(rows, list):
            raise ValueError("valuation snapshot is not a list")
        service.reconcile_valuations(rows)
        return True
    except Exception as error:
        log.warning("valuation_reconcile_failed", error=str(error))
        return False


def valuation_stream_consumer():
    while True:
        log.info("stream_connecting", url=VALUATION_STREAM_URL)
        try:
            request = urllib.request.Request(VALUATION_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                write_audit(SERVICE_NAME, "STREAM_CONNECTED", "Connected to valuation stream")
                if not _reconcile_valuations():
                    raise RuntimeError("valuation snapshot reconciliation failed")
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
