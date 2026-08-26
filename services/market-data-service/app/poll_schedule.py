import time


class PollSchedule:
    """When each symbol is next due. Tier 1 (open trades, benchmark) polls first."""

    def __init__(self):
        self._due = {}

    def due_entries(self, entries):
        now = time.monotonic()
        return sorted(
            (entry for entry in entries if self._due.get(entry.symbol, 0) <= now),
            key=lambda entry: (entry.tier, entry.symbol),
        )

    def defer(self, symbol, seconds):
        self._due[symbol] = time.monotonic() + seconds

    def next_due_seconds(self, entries):
        due = [self._due.get(entry.symbol, 0) for entry in entries]
        return None if not due else max(0, round(min(due) - time.monotonic()))

    def keep_only(self, entries):
        keep = {entry.symbol for entry in entries}
        for symbol in list(self._due):
            if symbol not in keep:
                del self._due[symbol]
