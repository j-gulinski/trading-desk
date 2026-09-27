import threading
import time
from concurrent.futures import ThreadPoolExecutor

from market_data_service import watchlist
from market_data_service.feeds import SEARCH_FEEDS
from market_data_service.providers.alpha_vantage.normalizer import attach_search_result
from desk_runtime.logging_config import get_logger
from market_data_service.config import (
    SERVICE_NAME,
    SYMBOL_SEARCH_CACHE_SECONDS,
    SYMBOL_SEARCH_RESULT_LIMIT,
)

log = get_logger(SERVICE_NAME)

_cache_lock = threading.Lock()
_cache = {}


def _rank(query):
    canonical_query = query.replace("/", "")

    def key(result):
        symbol = result["symbol"]
        provider_symbol = result["provider_symbol"]
        provider_exact = 0 if provider_symbol == query else 1
        exact = 0 if symbol == canonical_query else 1
        prefix = 0 if symbol.startswith(canonical_query) else 1
        return (provider_exact, exact, prefix, len(symbol), symbol, result["provider"])
    return key


def _provider_results(feed, query):
    try:
        found = feed.search(query)
    except Exception as error:
        log.exception("symbol_search_failed", provider=feed.provider)
        return [], feed.provider, f"unexpected {type(error).__name__}"
    if found is None:
        return [], feed.provider, "provider search is unavailable or out of budget"
    seen = set()
    results = []
    for result in sorted(found, key=_rank(query)):
        if result["symbol"] in seen:
            continue
        seen.add(result["symbol"])
        results.append(result)
    return results[:SYMBOL_SEARCH_RESULT_LIMIT], feed.provider, None


def _collect(query):
    with ThreadPoolExecutor(max_workers=len(SEARCH_FEEDS)) as pool:
        parts = list(pool.map(lambda feed: _provider_results(feed, query), SEARCH_FEEDS))
    results = sorted(
        (result for part, _, _ in parts for result in part),
        key=_rank(query),
    )
    attached = []
    seen = {(result["provider"], result["symbol"]) for result in results}
    for result in (*results, *watchlist.matching_identities(query)):
        candidate = attach_search_result(result)
        if candidate is None:
            continue
        key = (candidate["provider"], candidate["symbol"])
        if key in seen:
            continue
        seen.add(key)
        attached.append(candidate)
    results = sorted((*results, *attached), key=_rank(query))
    errors = {provider: error for _, provider, error in parts if error is not None}
    return results, errors


def search(query):
    query = query.strip().upper()
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(query)
        if cached and cached[0] > now:
            return cached[1], {}
    results, errors = _collect(query)
    if not errors:
        with _cache_lock:
            if len(_cache) > 200:
                _cache.clear()
            _cache[query] = (now + SYMBOL_SEARCH_CACHE_SECONDS, results)
    return results, errors
