from shared.providers import PROVIDERS
from app import finnhub_feed, twelve_data_feed

FEEDS = {feed.PROVIDER: feed for feed in (finnhub_feed, twelve_data_feed)}

POLL_LOOPS = tuple(feed.poll_loop for feed in FEEDS.values())

DEFAULT_PROVIDER = finnhub_feed.PROVIDER


def wired_quote_providers():
    return list(FEEDS)


def stale_after_seconds(provider, symbol):
    feed = FEEDS.get(provider, finnhub_feed)
    return feed.stale_after_seconds(symbol)


def closed_stale_after_seconds(provider, symbol):
    feed = FEEDS.get(provider, finnhub_feed)
    return feed.closed_stale_after_seconds(symbol)


def market_open(provider, symbol):
    feed = FEEDS.get(provider)
    return feed.market_open(symbol) if feed else None


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
        for symbol in sorted(feed.active_symbols()):
            tick, error, _ = feed.refresh_symbol(symbol)
            if error is None:
                refreshed.append({"provider": feed.PROVIDER, "symbol": symbol})
            else:
                skipped.append({"provider": feed.PROVIDER, "symbol": symbol,
                                "reason": error})
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
