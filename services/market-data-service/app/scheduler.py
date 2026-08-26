from app.providers import REGISTRATIONS
from shared.curves import curve_provider
from shared.providers import FINNHUB, PROVIDERS, QUOTE_PROVIDERS

SYMBOL_QUOTE_FEEDS = {
    provider.name: provider.quote_feed
    for provider in REGISTRATIONS
    if provider.quote_mode == "symbol"
}

TABLE_QUOTE_FEEDS = {
    provider.name: provider.quote_feed
    for provider in REGISTRATIONS
    if provider.quote_mode == "table"
}

QUOTE_FEEDS = {
    **SYMBOL_QUOTE_FEEDS,
    **TABLE_QUOTE_FEEDS,
}

CURVE_FEEDS = {
    provider.name: provider.curve_feed
    for provider in REGISTRATIONS
    if provider.curve_feed is not None
}

PROVIDER_HEALTH_READERS = {
    provider.name: provider.runtime_snapshot
    for provider in REGISTRATIONS
}

POLL_LOOPS = tuple(
    loop
    for provider in REGISTRATIONS
    for loop in provider.poll_loops()
)

DEFAULT_PROVIDER = FINNHUB


def wired_providers():
    return list(PROVIDER_HEALTH_READERS)


def wired_quote_providers():
    return [name for name in QUOTE_FEEDS if name in QUOTE_PROVIDERS]


def reload_active_set():
    for feed in QUOTE_FEEDS.values():
        feed.reload_active()


def refresh_symbol(symbol, provider=None):
    selected = provider or DEFAULT_PROVIDER
    feed = QUOTE_FEEDS.get(selected)
    if feed is None:
        if selected in CURVE_FEEDS:
            return None, f"{selected} serves curves, not quotes", 422
        return None, f"unknown or unwired provider: {provider}", 404
    return feed.refresh_symbol(symbol)


def refresh_all(provider=None):
    if provider is not None and provider not in PROVIDER_HEALTH_READERS:
        return [], [{"provider": provider, "reason": "unknown or unwired provider"}]
    if provider is not None and provider not in QUOTE_FEEDS:
        return [], []
    feeds = (
        [(provider, QUOTE_FEEDS[provider])]
        if provider is not None else list(QUOTE_FEEDS.items())
    )
    refreshed, skipped = [], []
    for name, feed in feeds:
        if name in TABLE_QUOTE_FEEDS:
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
        name: feed for name, feed in CURVE_FEEDS.items()
        if provider is None or name == provider
    }


def curve_provider_of(curve_name):
    return curve_provider(curve_name)


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
        feed_refreshed, feed_skipped = feed.refresh_all()
        refreshed.extend(feed_refreshed)
        skipped.extend(feed_skipped)
    return refreshed, skipped


def providers_overview():
    return [
        {
            "provider": name,
            "group": spec["group"],
            "wired": name in PROVIDER_HEALTH_READERS,
            "quotes": spec["quotes"],
            "serves_curves": spec["serves_curves"],
            **(
                {"runtime": PROVIDER_HEALTH_READERS[name]()}
                if name in PROVIDER_HEALTH_READERS else {}
            ),
        }
        for name, spec in PROVIDERS.items()
    ]


def provider_health(name):
    if name not in PROVIDERS:
        return None
    detail = {"provider": name, "wired": name in PROVIDER_HEALTH_READERS}
    if name in PROVIDER_HEALTH_READERS:
        detail.update(PROVIDER_HEALTH_READERS[name]())
    return detail
