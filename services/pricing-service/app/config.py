import os

from shared.config import MARKET_DATA_STREAM_URL, LOG_LEVEL
from shared.pricing_math import MINIMUM_OBSERVATIONS

SERVICE_NAME = "pricing-service"
HOST = "0.0.0.0"
PORT = 8002

TRADE_REFRESH_SECONDS = 2
VALUATION_STREAM_QUEUE_SIZE = 5000

# Book risk (alpha/beta) — see docs/alpha-beta.md.
# The capital base is the assumed capital per book that turns a PnL series into a
# return series; alpha and beta both scale as 1/capital_base, so it is surfaced in
# every published metric instead of being buried as a magic constant.
BOOK_RISK_WINDOW = int(os.environ.get("BOOK_RISK_WINDOW", "100"))
BOOK_RISK_MINIMUM_OBSERVATIONS = int(
    os.environ.get("BOOK_RISK_MINIMUM_OBSERVATIONS", str(MINIMUM_OBSERVATIONS))
)
BOOK_CAPITAL_BASE = float(os.environ.get("BOOK_CAPITAL_BASE", "1000000"))
# Capital assumed for the aggregated PORTFOLIO metric. Unset (default) means
# BOOK_CAPITAL_BASE × number of books — the capital the per-book convention implies.
PORTFOLIO_CAPITAL_BASE = os.environ.get("PORTFOLIO_CAPITAL_BASE") or None
