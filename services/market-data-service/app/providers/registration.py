"""One capability contract used to register every market-data provider."""

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from shared.curves import curve_names_for_provider
from shared.providers import PROVIDERS

QuoteMode = Literal["symbol", "table"]


class QuoteFeed(Protocol):
    PROVIDER: str

    def poll_loop(self): ...
    def refresh_symbol(self, symbol): ...
    def reload_active(self): ...
    def active_symbols(self): ...
    def runtime_snapshot(self): ...


class CurveFeedContract(Protocol):
    provider: str

    def poll_loop(self): ...
    def refresh_curve(self, curve_name): ...
    def refresh_all(self): ...
    def curve_names(self): ...
    def runtime_snapshot(self): ...


@dataclass(frozen=True)
class ProviderRegistration:
    """Capabilities supplied by one provider package.

    Providers expose the same registration shape even when a capability is absent.
    The scheduler depends on this contract, not on provider-specific modules.
    """

    name: str
    quote_mode: QuoteMode | None = None
    quote_feed: QuoteFeed | None = None
    curve_feed: CurveFeedContract | None = None
    normalize_search: Callable[[dict], list[dict]] | None = None

    def __post_init__(self):
        capability = PROVIDERS.get(self.name)
        if capability is None:
            raise ValueError(f"{self.name} is missing from the domain provider catalog")
        if (self.quote_mode is None) != (self.quote_feed is None):
            raise ValueError(f"{self.name} quote_mode and quote_feed must be declared together")
        if bool(self.quote_feed) != bool(capability["quotes"]):
            raise ValueError(f"{self.name} quote registration disagrees with its capability")
        if bool(self.curve_feed) != bool(capability["serves_curves"]):
            raise ValueError(f"{self.name} curve registration disagrees with its capability")
        expected_curves = set(curve_names_for_provider(self.name))
        wired_curves = set(self.curve_feed.curve_names()) if self.curve_feed else set()
        if wired_curves != expected_curves:
            missing = sorted(expected_curves - wired_curves)
            unexpected = sorted(wired_curves - expected_curves)
            raise ValueError(
                f"{self.name} curve registration disagrees with the curve catalog: "
                f"missing={missing}, unexpected={unexpected}"
            )
        if self.quote_feed is not None and self.quote_feed.PROVIDER != self.name:
            raise ValueError(f"{self.name} quote feed declares {self.quote_feed.PROVIDER}")
        if self.curve_feed is not None and self.curve_feed.provider != self.name:
            raise ValueError(f"{self.name} curve feed declares {self.curve_feed.provider}")
        if self.normalize_search is not None and self.quote_mode != "symbol":
            raise ValueError(f"{self.name} search requires a symbol quote feed")

    def poll_loops(self):
        loops = []
        if self.quote_feed is not None:
            loops.append(self.quote_feed.poll_loop)
        if self.curve_feed is not None:
            loops.append(self.curve_feed.poll_loop)
        return tuple(loops)

    def runtime_snapshot(self):
        if self.quote_feed is not None:
            return self.quote_feed.runtime_snapshot()
        if self.curve_feed is not None:
            return self.curve_feed.runtime_snapshot()
        return {}

    def search(self, query):
        if self.normalize_search is None or self.quote_feed is None:
            return None
        return self.quote_feed.search(query)
