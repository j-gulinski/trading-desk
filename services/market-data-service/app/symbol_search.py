import threading
import time
from concurrent.futures import ThreadPoolExecutor

from shared.logging_config import get_logger
from shared.providers import FINNHUB, TWELVE_DATA
from shared.symbols import is_valid_symbol
from app import finnhub_feed, twelve_data_feed
from app.clients.base import ProviderError
from app.config import (
    SERVICE_NAME,
    SYMBOL_SEARCH_CACHE_SECONDS,
    SYMBOL_SEARCH_RESULT_LIMIT,
)

log = get_logger(SERVICE_NAME)

METAL_BASES = ("XAU", "XAG", "XPT", "XPD")

_cache_lock = threading.Lock()
_cache = {}


def _finnhub_results(payload):
    results = []
    for item in (payload.get("result") or []) if isinstance(payload, dict) else []:
        symbol = (item.get("symbol") or "").upper()
        if not is_valid_symbol(symbol):
            continue
        results.append({
            "provider": FINNHUB,
            "symbol": symbol,
            "provider_symbol": symbol,
            "name": item.get("description") or symbol,
            "asset_class": "EQUITY",
            "currency": "USD",
            "exchange": "US",
        })
    return results


def _twelve_data_results(payload):
    results = []
    for item in (payload.get("data") or []) if isinstance(payload, dict) else []:
        raw = (item.get("symbol") or "").upper()
        if "/" in raw:
            base, _, quote = raw.partition("/")
            symbol = f"{base}{quote}"
            asset_class = "COMMODITY" if base in METAL_BASES else "FX"
            currency = quote
        else:
            symbol = raw
            asset_class = "EQUITY"
            currency = (item.get("currency") or "USD").upper()
        if not is_valid_symbol(symbol):
            continue
        results.append({
            "provider": TWELVE_DATA,
            "symbol": symbol,
            "provider_symbol": raw,
            "name": item.get("instrument_name") or symbol,
            "asset_class": asset_class,
            "currency": currency,
            "exchange": item.get("exchange") or None,
        })
    return results


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


def _provider_results(source, query):
    fetch, normalize, provider = source
    try:
        payload = fetch(query)
    except ProviderError as error:
        log.warning("symbol_search_failed", provider=provider, detail=error.detail)
        return []
    if payload is None:
        return []
    seen = set()
    results = []
    for result in sorted(normalize(payload), key=_rank(query)):
        if result["symbol"] in seen:
            continue
        seen.add(result["symbol"])
        results.append(result)
    return results[:SYMBOL_SEARCH_RESULT_LIMIT]


def _collect(query):
    sources = (
        (finnhub_feed.search, _finnhub_results, FINNHUB),
        (twelve_data_feed.search, _twelve_data_results, TWELVE_DATA),
    )
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        parts = pool.map(lambda source: _provider_results(source, query), sources)
    return sorted((result for part in parts for result in part), key=_rank(query))


def search(query):
    query = query.strip().upper()
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(query)
        if cached and cached[0] > now:
            return cached[1]
    results = _collect(query)
    with _cache_lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[query] = (now + SYMBOL_SEARCH_CACHE_SECONDS, results)
    return results
