import time
import uuid
from datetime import timedelta

from shared.db import session_scope
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.models import MarketDataSnapshot, MarketDataSpotPrice, Trade
from app.config import (
    RETENTION_SWEEP_INTERVAL_SECONDS,
    SERVICE_NAME,
    SNAPSHOT_RETENTION_DAYS,
)

log = get_logger(SERVICE_NAME)

PRICE_FIELDS = ("bid", "ask", "last", "mid")
QUOTE_FIELDS = PRICE_FIELDS + (
    "provider",
    "symbol",
    "asset_class",
    "currency",
    "price_basis",
    "quote_grade",
    "provider_timestamp",
    "received_at",
)


def store_quote(quote):
    """Board upsert plus change-only history append; returns True when the price moved."""
    with session_scope() as session:
        row = (
            session.query(MarketDataSpotPrice)
            .filter_by(provider=quote.provider, symbol=quote.symbol)
            .with_for_update()
            .one_or_none()
        )
        changed = row is None or any(
            getattr(row, field) != getattr(quote, field) for field in PRICE_FIELDS
        )
        now = utcnow()
        if row is None:
            row = MarketDataSpotPrice(
                market_data_id=uuid.uuid4(),
                provider=quote.provider,
                symbol=quote.symbol,
                created_at=now,
            )
            session.add(row)
        for field in QUOTE_FIELDS:
            setattr(row, field, getattr(quote, field))
        if changed:
            session.add(
                MarketDataSnapshot(
                    snapshot_id=uuid.uuid4(),
                    created_at=now,
                    raw_payload=quote.raw_payload,
                    **{field: getattr(quote, field) for field in QUOTE_FIELDS},
                )
            )
        return changed


def board_rows():
    with session_scope() as session:
        rows = (
            session.query(MarketDataSpotPrice)
            .order_by(MarketDataSpotPrice.provider, MarketDataSpotPrice.symbol)
            .all()
        )
        return [{field: getattr(row, field) for field in QUOTE_FIELDS} for row in rows]


def sweep_snapshots():
    cutoff = utcnow() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    with session_scope() as session:
        referenced = session.query(Trade.entry_snapshot_id).filter(
            Trade.entry_snapshot_id.isnot(None)
        )
        deleted = (
            session.query(MarketDataSnapshot)
            .filter(
                MarketDataSnapshot.received_at < cutoff,
                ~MarketDataSnapshot.snapshot_id.in_(referenced),
            )
            .delete(synchronize_session=False)
        )
    log.info(
        "snapshot_retention_swept", deleted=deleted, retention_days=SNAPSHOT_RETENTION_DAYS
    )
    return deleted


def retention_sweep_loop():
    while True:
        try:
            sweep_snapshots()
        except Exception:
            log.exception("snapshot_retention_failed")
        time.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
