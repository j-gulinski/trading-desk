from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from market_data_service.config import OFFICIAL_FIXING_FEED_PUBLICATION_GRACE_SECONDS

BUSINESS_WEEKDAYS = range(5)


class PublicationCalendar:
    def __init__(self, tz_name, window_start, window_end):
        self.tz = ZoneInfo(tz_name)
        self.window_start = time(*window_start)
        self.window_end = time(*window_end)

    def source_today(self, now):
        return now.astimezone(self.tz).date()

    def in_window(self, now):
        local = now.astimezone(self.tz)
        return (
            local.weekday() in BUSINESS_WEEKDAYS
            and self.window_start <= local.time() <= self.window_end
        )

    def _next_publication_end(self, after_date):
        day = after_date + timedelta(days=1)
        while day.weekday() not in BUSINESS_WEEKDAYS:
            day += timedelta(days=1)
        return datetime.combine(day, self.window_end, tzinfo=self.tz)

    def stale_after_seconds(self, as_of_date):
        as_of = datetime.combine(as_of_date, time(0, 0), tzinfo=timezone.utc)
        deadline = self._next_publication_end(as_of_date).astimezone(timezone.utc)
        return round(
            (deadline - as_of).total_seconds()
            + OFFICIAL_FIXING_FEED_PUBLICATION_GRACE_SECONDS
        )

    def next_window_seconds(self, now):
        if self.in_window(now):
            return 0
        local = now.astimezone(self.tz)
        day = local.date()
        if local.weekday() not in BUSINESS_WEEKDAYS or local.time() > self.window_start:
            day = self._next_publication_end(day).date()
        opens = datetime.combine(day, self.window_start, tzinfo=self.tz)
        return round((opens - local).total_seconds())

    def describe_window(self):
        start = self.window_start.strftime("%H:%M")
        end = self.window_end.strftime("%H:%M")
        city = self.tz.key.split("/")[-1].replace("_", " ")
        return f"{start}–{end} {city} time, business days"
