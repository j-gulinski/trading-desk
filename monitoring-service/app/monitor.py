import time
import json
import logging
import threading
import urllib.request
import urllib.error
from shared import get_iso_timestamp
from app.config import MARKET_DATA_SERVICE_HEALTHCHECK_URL, PRICING_SERVICE_HEALTHCHECK_URL

lock = threading.Lock()
monitoring_state = {
    "market-data-service": {"status": "UNKNOWN"},
    "pricing-service": {"status": "UNKNOWN"},
}


def market_data_monitoring_loop():
    monitoring_loop(MARKET_DATA_SERVICE_HEALTHCHECK_URL, "market-data-service")


def pricing_monitoring_loop():
    monitoring_loop(PRICING_SERVICE_HEALTHCHECK_URL, "pricing-service")


def monitoring_loop(url, service_name):
    while True:
        logging.debug(f"Checking health of {service_name}...")
        start_time = time.time()
        current_time = get_iso_timestamp()
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=3) as http_response:
                raw_data = http_response.read()
                response_time_ms = int((time.time() - start_time) * 1000)
                try:
                    health_data = json.loads(raw_data.decode("utf-8"))
                    service_status = health_data.get("status", "UNKNOWN")
                except json.JSONDecodeError:
                    service_status = "UNKNOWN"
                    logging.error(
                        f"Failed to decode health check response from {service_name}: {raw_data}"
                    )

                with lock:
                    if service_status == "UP" and monitoring_state[service_name].get("status") != "UP":
                        logging.info(f"{service_name} is now UP")
                    monitoring_state[service_name] = {
                        "status": service_status,
                        "response_time_ms": response_time_ms,
                        "last_checked": current_time,
                    }
        except Exception as e:
            with lock:
                monitoring_state[service_name] = {
                    "status": "DOWN",
                    "last_checked": current_time,
                    "error": str(e),
                }
            logging.error(f"Health check failed for {service_name}: {e}")
        time.sleep(1)
