from shared.providers import PROVIDERS
from app import finnhub_feed

FEEDS = {finnhub_feed.PROVIDER: finnhub_feed}

POLL_LOOPS = tuple(feed.poll_loop for feed in FEEDS.values())


def stale_after_seconds(provider, symbol):
    feed = FEEDS.get(provider, finnhub_feed)
    return feed.stale_after_seconds(symbol)


def refresh_symbol(symbol):
    return finnhub_feed.refresh_symbol(symbol)


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
