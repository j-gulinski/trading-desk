"""Serialize quote publication with watchlist/provider removal per board key."""

from contextlib import contextmanager
import threading


_registry_lock = threading.Lock()
_locks = {}


def _key_lock(provider, symbol):
    key = (provider, symbol)
    with _registry_lock:
        return _locks.setdefault(key, threading.Lock())


@contextmanager
def locked_keys(symbol, providers):
    locks = [_key_lock(provider, symbol) for provider in sorted(set(providers))]
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()
