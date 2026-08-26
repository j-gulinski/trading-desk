import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.providers import REGISTRATIONS
from app.providers.base import ProviderError
from shared.logging_config import get_logger
from app.config import (
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


def _provider_results(provider, query):
    try:
        payload = provider.search(query)
    except ProviderError as error:
        log.warning("symbol_search_failed", provider=provider.name, detail=error.detail)
        return [], provider.name, error.detail
    except Exception as error:
        log.exception("symbol_search_failed", provider=provider.name)
        return [], provider.name, f"unexpected {type(error).__name__}"
    if payload is None:
        return [], provider.name, "provider search is unavailable or out of budget"
    seen = set()
    results = []
    for result in sorted(provider.normalize_search(payload), key=_rank(query)):
        if result["symbol"] in seen:
            continue
        seen.add(result["symbol"])
        results.append(result)
    return results[:SYMBOL_SEARCH_RESULT_LIMIT], provider.name, None


def _collect(query):
    providers = tuple(
        provider for provider in REGISTRATIONS
        if provider.normalize_search is not None
    )
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        parts = list(pool.map(lambda provider: _provider_results(provider, query), providers))
    results = sorted(
        (result for part, _, _ in parts for result in part),
        key=_rank(query),
    )
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
    # Never turn an outage or exhausted search budget into a cached "no matches" fact.
    if not errors:
        with _cache_lock:
            if len(_cache) > 200:
                _cache.clear()
            _cache[query] = (now + SYMBOL_SEARCH_CACHE_SECONDS, results)
    return results, errors
