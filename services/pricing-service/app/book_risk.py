from collections import defaultdict, deque

from app import cache
from app.config import (
    BOOK_CAPITAL_BASE,
    BOOK_RISK_MINIMUM_OBSERVATIONS,
    BOOK_RISK_WINDOW,
    PORTFOLIO_CAPITAL_BASE,
)
from app.valuation_publisher import publish_book_risk
from shared.catalog import BENCHMARK_SYMBOL
from shared.functions import get_iso_timestamp
from shared.pricing_math import alpha_beta

PORTFOLIO_ID = "PORTFOLIO"
PORTFOLIO_NAME = "All books"


class BookRiskEngine:
    """Rolling alpha/beta per book against the benchmark. See docs/alpha-beta.md.

    Samples are stored in dollar space — (ΔPnL, benchmark return) pairs — and the
    capital base divides in only at publish time, so a config change rescales output
    without invalidating the window, and the PORTFOLIO aggregate is a plain PnL sum.
    """

    def __init__(
        self,
        window=BOOK_RISK_WINDOW,
        minimum_observations=BOOK_RISK_MINIMUM_OBSERVATIONS,
        capital_base=BOOK_CAPITAL_BASE,
        portfolio_capital_base=PORTFOLIO_CAPITAL_BASE,
    ):
        self.window = window
        self.minimum_observations = minimum_observations
        self.capital_base = float(capital_base)
        self.portfolio_capital_base = (
            float(portfolio_capital_base) if portfolio_capital_base else None
        )
        self.previous_benchmark = None
        self.previous_pnl = {}
        self.samples = defaultdict(lambda: deque(maxlen=window))

    def update(self, benchmark_level, books):
        benchmark_level = float(benchmark_level)
        if benchmark_level <= 0:
            return []

        benchmark_return = None
        if self.previous_benchmark is not None and self.previous_benchmark > 0:
            benchmark_return = benchmark_level / self.previous_benchmark - 1.0
        self.previous_benchmark = benchmark_level

        books = dict(books)
        book_count = len(books)
        if books:
            books[PORTFOLIO_ID] = {
                "book_name": PORTFOLIO_NAME,
                "pnl": sum(float(book["pnl"]) for book in books.values()),
            }

        self._drop_absent_books(books)

        events = []
        for book_id, book in books.items():
            pnl = float(book["pnl"])
            previous_pnl = self.previous_pnl.get(book_id)
            self.previous_pnl[book_id] = pnl
            if benchmark_return is not None and previous_pnl is not None:
                self.samples[book_id].append((pnl - previous_pnl, benchmark_return))
            events.append(self._metric(book_id, book.get("book_name"), book_count))
        return events

    def _drop_absent_books(self, books):
        for book_id in list(self.previous_pnl):
            if book_id not in books:
                del self.previous_pnl[book_id]
                self.samples.pop(book_id, None)

    def _capital_for(self, book_id, book_count):
        if book_id != PORTFOLIO_ID:
            return self.capital_base
        if self.portfolio_capital_base is not None:
            return self.portfolio_capital_base
        return self.capital_base * max(1, book_count)

    def _benchmark_context(self, benchmark_returns):
        # Must be the sum the regression consumed; a compounded move would not close the identity.
        return {
            "benchmark_level": self.previous_benchmark,
            "benchmark_window_return": sum(benchmark_returns) if benchmark_returns else None,
        }

    def _metric(self, book_id, book_name, book_count):
        pairs = self.samples[book_id]
        pnl_changes = [pair[0] for pair in pairs]
        benchmark_returns = [pair[1] for pair in pairs]
        result = alpha_beta(pnl_changes, benchmark_returns, self.minimum_observations)

        capital = self._capital_for(book_id, book_count)
        dollar_alpha = result["alpha"]
        dollar_beta = result["beta"]
        alpha = dollar_alpha / capital if dollar_alpha is not None else None
        observations = len(pairs)
        book_window_pnl = sum(pnl_changes) if pnl_changes else None
        return {
            "book_id": book_id,
            "book_name": book_name,
            "is_portfolio": book_id == PORTFOLIO_ID,
            "benchmark": BENCHMARK_SYMBOL,
            **self._benchmark_context(benchmark_returns),
            "capital_base": capital,
            "observations": observations,
            "window": self.window,
            "minimum_observations": self.minimum_observations,
            "book_window_pnl": book_window_pnl,
            "book_window_return": (
                book_window_pnl / capital if book_window_pnl is not None else None
            ),
            "alpha": alpha,
            "alpha_window_return": alpha * observations if alpha is not None else None,
            "alpha_window_pnl": (
                dollar_alpha * observations if dollar_alpha is not None else None
            ),
            "beta": dollar_beta / capital if dollar_beta is not None else None,
            "dollar_beta": dollar_beta,
            "r_squared": result["r_squared"],
            "status": result["status"],
            "calculated_at": get_iso_timestamp(),
        }


engine = BookRiskEngine()


def sample_and_publish(benchmark_level):
    events = engine.update(benchmark_level, cache.book_pnl_snapshot())
    for event in events:
        cache.set_book_risk(event)
        publish_book_risk(event)
    return events
