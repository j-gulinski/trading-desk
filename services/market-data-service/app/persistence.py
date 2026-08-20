import time
import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from shared.db import session_scope
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.models import MarketDataSnapshot, MarketDataSpotPrice, Trade
from shared.active_set import load_active_set
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
SESSION_FIELDS = ("previous_close",)
CLASSIFIER_FIELDS = ("stale_after_seconds", "closed_stale_after_seconds", "market_open")


def _store_quote(quote, classifier):
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
        created = row is None
        if row is None:
            row = MarketDataSpotPrice(
                market_data_id=uuid.uuid4(),
                provider=quote.provider,
                symbol=quote.symbol,
                created_at=now,
            )
            session.add(row)
        for field in QUOTE_FIELDS + SESSION_FIELDS:
            setattr(row, field, getattr(quote, field))
        for field in CLASSIFIER_FIELDS:
            setattr(row, field, classifier.get(field))
        if changed:
            snapshot_id = uuid.uuid4()
            session.add(
                MarketDataSnapshot(
                    snapshot_id=snapshot_id,
                    created_at=now,
                    raw_payload=quote.raw_payload,
                    **{field: getattr(quote, field) for field in QUOTE_FIELDS},
                )
            )
            session.flush()
            row.latest_snapshot_id = snapshot_id
        return changed, created


def store_quote(quote, classifier):
    try:
        return _store_quote(quote, classifier)
    except IntegrityError:
        # Two first polls can race before there is a board row to lock.
        return _store_quote(quote, classifier)


def board_rows():
    with session_scope() as session:
        rows = (
            session.query(MarketDataSpotPrice)
            .order_by(MarketDataSpotPrice.provider, MarketDataSpotPrice.symbol)
            .all()
        )
        return [
            {
                **{field: getattr(row, field) for field in QUOTE_FIELDS + SESSION_FIELDS},
                **{field: getattr(row, field) for field in CLASSIFIER_FIELDS},
                "latest_snapshot_id": row.latest_snapshot_id,
            }
            for row in rows
        ]


def quote_history(provider, symbol, limit):
    with session_scope() as session:
        rows = (
            session.query(MarketDataSnapshot)
            .filter_by(provider=provider, symbol=symbol)
            .order_by(MarketDataSnapshot.received_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "provider": provider,
            "symbol": symbol,
            "mode": "observed_changes",
            "rows": [
                {
                    "snapshot_id": row.snapshot_id,
                    "asset_class": row.asset_class,
                    "currency": row.currency,
                    "bid": row.bid,
                    "ask": row.ask,
                    "last": row.last,
                    "mid": row.mid,
                    "price_basis": row.price_basis,
                    "quote_grade": row.quote_grade,
                    "provider_timestamp": row.provider_timestamp,
                    "received_at": row.received_at,
                }
                for row in rows
            ],
        }


def delete_board_rows(symbol, providers=None):
    with session_scope() as session:
        query = session.query(MarketDataSpotPrice).filter_by(symbol=symbol)
        if providers is not None:
            query = query.filter(MarketDataSpotPrice.provider.in_(list(providers)))
        deleted = query.delete(synchronize_session=False)
    if deleted:
        log.info("board_rows_removed", symbol=symbol, rows=deleted)
    return deleted


def sweep_snapshots():
    cutoff = utcnow() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    with session_scope() as session:
        by_trades = session.query(Trade.entry_snapshot_id).filter(
            Trade.entry_snapshot_id.isnot(None)
        )
        by_closes = session.query(Trade.close_snapshot_id).filter(
            Trade.close_snapshot_id.isnot(None)
        )
        by_board = session.query(MarketDataSpotPrice.latest_snapshot_id).filter(
            MarketDataSpotPrice.latest_snapshot_id.isnot(None)
        )
        deleted = (
            session.query(MarketDataSnapshot)
            .filter(
                MarketDataSnapshot.received_at < cutoff,
                ~MarketDataSnapshot.snapshot_id.in_(by_trades),
                ~MarketDataSnapshot.snapshot_id.in_(by_closes),
                ~MarketDataSnapshot.snapshot_id.in_(by_board),
            )
            .delete(synchronize_session=False)
        )
    log.info(
        "snapshot_retention_swept", deleted=deleted, retention_days=SNAPSHOT_RETENTION_DAYS
    )
    return deleted


def sweep_board_strays():
    active = load_active_set()
    with session_scope() as session:
        rows = session.query(
            MarketDataSpotPrice.market_data_id,
            MarketDataSpotPrice.provider,
            MarketDataSpotPrice.symbol,
        ).all()
        stray = [
            market_data_id
            for market_data_id, provider, symbol in rows
            if symbol not in active or not active[symbol].serves(provider)
        ]
        if not stray:
            return 0
        deleted = (
            session.query(MarketDataSpotPrice)
            .filter(MarketDataSpotPrice.market_data_id.in_(stray))
            .delete(synchronize_session=False)
        )
    if deleted:
        log.info("board_strays_swept", rows=deleted)
    return deleted


def retention_sweep_loop():
    while True:
        for sweep in (sweep_snapshots, sweep_board_strays):
            try:
                sweep()
            except Exception:
                log.exception("retention_sweep_failed", sweep=sweep.__name__)
        time.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
