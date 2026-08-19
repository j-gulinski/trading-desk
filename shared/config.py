import os


def env_str(name, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_int(name, default=None):
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def env_float(name, default=None):
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def env_required(name):
    raw = os.environ.get(name)
    if raw in (None, ""):
        raise RuntimeError(f"{name} is not set")
    return raw


DATABASE_URL = env_required("DATABASE_URL")

BENCHMARK_SYMBOL = env_str("BENCHMARK_SYMBOL", "SPY")
BENCHMARK_PROVIDER = env_str("BENCHMARK_PROVIDER", "FINNHUB")

LOG_LEVEL = env_str("LOG_LEVEL", "INFO")
LOG_DIR = env_str("LOG_DIR")
LOG_FILE_MAX_BYTES = env_int("LOG_FILE_MAX_BYTES", 5_000_000)
LOG_FILE_BACKUP_COUNT = env_int("LOG_FILE_BACKUP_COUNT", 3)
