import json
import sys
import time
import urllib.request

from desk_day.universe import SYMBOL_COUNT
from desk_runtime.config import SERVICE_URLS

TIMEOUT_SECONDS = 300
POLL_SECONDS = 5
MIN_LIVE_VALUATIONS = 4_900


def get(service, path):
    with urllib.request.urlopen(f"{SERVICE_URLS[service]}{path}", timeout=30) as response:
        return json.load(response)


def desk_state():
    spots = get("market-data-service", "/snapshot")["spots"].values()
    connection = get("pricing-service", "/health").get("market_data_connection")
    valuations = get("pricing-service", "/valuations")
    return (
        sum(spot.get("freshness") == "LIVE" for spot in spots),
        connection,
        sum((row.get("valuation_payload") or {}).get("status") == "LIVE" for row in valuations),
    )


def main():
    started = time.monotonic()
    while time.monotonic() - started < TIMEOUT_SECONDS:
        try:
            live_spots, connection, live_valuations = desk_state()
        except (OSError, ValueError) as error:
            print(f"{time.monotonic() - started:5.0f} s  not reachable: {error}", flush=True)
        else:
            print(
                f"{time.monotonic() - started:5.0f} s  live spots {live_spots}/{SYMBOL_COUNT}  "
                f"pricing {connection}  live valuations {live_valuations}",
                flush=True,
            )
            if (live_spots >= SYMBOL_COUNT and connection == "CONNECTED"
                    and live_valuations >= MIN_LIVE_VALUATIONS):
                return 0
        time.sleep(POLL_SECONDS)
    return 1


if __name__ == "__main__":
    sys.exit(main())
