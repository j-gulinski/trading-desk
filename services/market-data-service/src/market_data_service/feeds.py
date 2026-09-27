"""Every wired provider feed, and requests routed to the feed that serves them."""

from desk_domain.providers import PROVIDERS
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from market_data_service.providers.alpha_vantage.feed import feed as alpha_vantage
from market_data_service.providers.ecb.feed import curve_feed as ecb_curves
from market_data_service.providers.ecb.feed import fixing_feed as ecb_fixings
from market_data_service.providers.eiopa.feed import curve_feed as eiopa
from market_data_service.providers.finnhub.feed import feed as finnhub
from market_data_service.providers.fred.feed import curve_feed as fred
from market_data_service.providers.nbp.feed import feed as nbp
from market_data_service.providers.twelve_data.feed import feed as twelve_data

SYMBOL_FEEDS = (finnhub, twelve_data, alpha_vantage)
SEARCH_FEEDS = (finnhub, twelve_data)
QUOTE_FEEDS = {feed.provider: feed for feed in (*SYMBOL_FEEDS, nbp, ecb_fixings)}
CURVE_FEEDS = {feed.provider: feed for feed in (ecb_curves, fred, eiopa)}
POLL_LOOPS = tuple(feed.poll_loop for feed in (*QUOTE_FEEDS.values(), *CURVE_FEEDS.values()))

WATCHLIST_PROVIDERS = tuple(feed.provider for feed in SYMBOL_FEEDS)
WIRED_PROVIDERS = frozenset((*QUOTE_FEEDS, *CURVE_FEEDS))


def runtime_snapshot(provider):
    quote_feed, curve_feed = QUOTE_FEEDS.get(provider), CURVE_FEEDS.get(provider)
    if quote_feed is None:
        return curve_feed.runtime_snapshot()
    snapshot = quote_feed.runtime_snapshot()
    if curve_feed is None:
        return snapshot
    return {
        **snapshot,
        "curves": curve_feed.curve_names(),
        "curve_strategy": curve_feed.strategy(),
        "feeds": {"fixings": snapshot, "curves": curve_feed.runtime_snapshot()},
    }


def providers_overview():
    return [
        {
            "provider": name,
            "group": spec["group"],
            "wired": name in WIRED_PROVIDERS,
            "quotes": spec["quotes"],
            "serves_curves": spec["serves_curves"],
            **({"runtime": runtime_snapshot(name)} if name in WIRED_PROVIDERS else {}),
        }
        for name, spec in PROVIDERS.items()
    ]


def refresh_symbol(symbol, provider=None):
    """Returns (tick, error, http_status)."""
    selected = provider or DEFAULT_QUOTE_PROVIDER
    feed = QUOTE_FEEDS.get(selected)
    if feed is None:
        if selected in CURVE_FEEDS:
            return None, f"{selected} serves curves, not quotes", 422
        return None, f"unknown or unwired provider: {provider}", 404
    return feed.refresh_symbol(symbol)


def refresh_all(provider=None):
    """Returns (refreshed, skipped) over every quote feed, or one provider's."""
    if provider is None:
        feeds = list(QUOTE_FEEDS.values())
    elif provider in QUOTE_FEEDS:
        feeds = [QUOTE_FEEDS[provider]]
    elif provider in CURVE_FEEDS:
        return [], []
    else:
        return [], [{"provider": provider, "reason": "unknown or unwired provider"}]
    refreshed, skipped = [], []
    for feed in feeds:
        feed_refreshed, feed_skipped = feed.refresh_all()
        refreshed.extend(feed_refreshed)
        skipped.extend(feed_skipped)
    return refreshed, skipped
