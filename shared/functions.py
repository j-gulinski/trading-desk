import datetime


def utcnow() -> datetime.datetime:
    """Timezone-aware 'now' for TIMESTAMPTZ columns."""
    return datetime.datetime.now(datetime.timezone.utc)


def get_iso_timestamp() -> str:
    """Millisecond ISO-8601 string, e.g. 2026-06-01T19:19:04.435Z."""
    return utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def first_present(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None
