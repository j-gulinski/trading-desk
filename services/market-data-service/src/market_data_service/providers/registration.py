from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProviderRegistration:
    name: str
    quote_mode: str | None = None
    quote_feed: object = None
    curve_feed: object = None
    normalize_search: Callable | None = None
    attach_search: Callable | None = None

    def poll_loops(self):
        return tuple(feed.poll_loop for feed in (self.quote_feed, self.curve_feed) if feed is not None)

    def runtime_snapshot(self):
        return (self.quote_feed or self.curve_feed).runtime_snapshot()

    def search(self, query):
        return self.quote_feed.search(query)
