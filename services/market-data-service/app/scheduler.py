from shared.providers import PROVIDERS, QUOTE_PROVIDERS
from app import ecb_feed, finnhub_feed, fred_feed, nbp_feed, twelve_data_feed

FEEDS = {
    feed.PROVIDER: feed
    for feed in (finnhub_feed, twelve_data_feed, nbp_feed, ecb_feed, fred_feed)
}

POLL_LOOPS = tuple(
    loop
    for feed in FEEDS.values()
    for loop in getattr(feed, "poll_loops", (feed.poll_loop,))
)

DEFAULT_PROVIDER = finnhub_feed.PROVIDER


def wired_providers():
    return list(FEEDS)


def wired_quote_providers():
    return [name for name in FEEDS if name in QUOTE_PROVIDERS]


def reload_active_set():
    for feed in FEEDS.values():
        feed.reload_active()


def refresh_symbol(symbol, provider=None):
    feed = FEEDS.get(provider or DEFAULT_PROVIDER)
    if feed is None:
        return None, f"unknown or unwired provider: {provider}", 404
    return feed.refresh_symbol(symbol)


def refresh_all(provider=None):
    if provider is not None and provider not in FEEDS:
        return [], [{"provider": provider, "reason": "unknown or unwired provider"}]
    feeds = [FEEDS[provider]] if provider is not None else list(FEEDS.values())
    refreshed, skipped = [], []
    for feed in feeds:
        if hasattr(feed, "refresh_table"):
            table_refreshed, table_skipped = feed.refresh_table()
            refreshed.extend(table_refreshed)
            skipped.extend(table_skipped)
            continue
        for symbol in sorted(feed.active_symbols()):
            tick, error, _ = feed.refresh_symbol(symbol)
            if error is None:
                refreshed.append({"provider": feed.PROVIDER, "symbol": symbol})
            else:
                skipped.append({"provider": feed.PROVIDER, "symbol": symbol,
                                "reason": error})
    return refreshed, skipped


def _curve_feeds(provider=None):
    return {
        name: feed for name, feed in FEEDS.items()
        if hasattr(feed, "refresh_curves") and (provider is None or name == provider)
    }


def curve_provider_of(curve_name):
    for name, feed in _curve_feeds().items():
        if curve_name in feed.curve_names():
            return name
    return None


def refresh_curve(curve_name, provider=None):
    """Returns (entry, error, http_status)."""
    provider = provider or curve_provider_of(curve_name)
    feed = _curve_feeds().get(provider)
    if feed is None:
        return None, f"no wired curve source for {curve_name}", 404
    return feed.refresh_curve(curve_name)


def refresh_curves(provider=None):
    feeds = _curve_feeds(provider)
    if provider is not None and not feeds:
        return [], [{"provider": provider, "reason": "provider serves no curves"}]
    refreshed, skipped = [], []
    for feed in feeds.values():
        feed_refreshed, feed_skipped = feed.refresh_curves()
        refreshed.extend(feed_refreshed)
        skipped.extend(feed_skipped)
    return refreshed, skipped


def providers_overview():
    return [
        {
            "provider": name,
            "group": spec["group"],
            "wired": name in FEEDS,
            "quotes": spec["quotes"],
            "serves_curves": spec["serves_curves"],
            **({"runtime": FEEDS[name].runtime_snapshot()} if name in FEEDS else {}),
        }
        for name, spec in PROVIDERS.items()
    ]


def provider_health(name):
    if name not in PROVIDERS:
        return None
    detail = {"provider": name, "wired": name in FEEDS}
    if name in FEEDS:
        detail.update(FEEDS[name].runtime_snapshot())
    return detail
