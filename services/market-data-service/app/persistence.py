import time
import uuid
from datetime import timedelta

from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError

from shared.db import session_scope
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.models import (
    MarketDataCurve,
    MarketDataCurvePoint,
    MarketDataSnapshot,
    MarketDataSpotPrice,
    Trade,
)
from shared.active_set import load_active_set
from app import reference_set
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
SESSION_FIELDS = (
    "previous_close",
    "day_open",
    "day_high",
    "day_low",
    "week52_high",
    "week52_low",
    "volume",
    "average_volume",
)
CLASSIFIER_FIELDS = ("stale_after_seconds", "closed_stale_after_seconds", "market_open")
CURVE_POINT_FIELDS = ("tenor_label", "tenor_years", "rate", "source_series", "source_as_of")


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


def quote_history(provider, symbol, limit, include_raw=False):
    with session_scope() as session:
        # backfilled fixings share one received_at — the provider clock breaks the tie
        rows = (
            session.query(MarketDataSnapshot)
            .filter_by(provider=provider, symbol=symbol)
            .order_by(
                MarketDataSnapshot.received_at.desc(),
                MarketDataSnapshot.provider_timestamp.desc(),
            )
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
                    **({"raw_payload": row.raw_payload} if include_raw else {}),
                }
                for row in rows
            ],
        }


def sparse_history_symbols(provider, symbols):
    with session_scope() as session:
        counts = dict(
            session.query(
                MarketDataSnapshot.symbol,
                sa_func.count(MarketDataSnapshot.snapshot_id),
            )
            .filter(
                MarketDataSnapshot.provider == provider,
                MarketDataSnapshot.symbol.in_(list(symbols)),
            )
            .group_by(MarketDataSnapshot.symbol)
            .all()
        )
    return [symbol for symbol in symbols if counts.get(symbol, 0) <= 1]


def backfill_snapshots(provider, quotes):
    """Insert historical fixings as change-only snapshot rows, strictly older than
    anything already stored per symbol; the board is untouched."""
    inserted = 0
    by_symbol = {}
    for quote in quotes:
        by_symbol.setdefault(quote.symbol, []).append(quote)
    with session_scope() as session:
        for symbol, series in by_symbol.items():
            oldest = (
                session.query(sa_func.min(MarketDataSnapshot.provider_timestamp))
                .filter_by(provider=provider, symbol=symbol)
                .scalar()
            )
            previous_mid = None
            for quote in sorted(series, key=lambda item: item.provider_timestamp):
                if oldest is not None and quote.provider_timestamp >= oldest:
                    continue
                if previous_mid is not None and quote.mid == previous_mid:
                    continue
                previous_mid = quote.mid
                session.add(MarketDataSnapshot(
                    snapshot_id=uuid.uuid4(),
                    created_at=quote.received_at,
                    raw_payload=quote.raw_payload,
                    **{field: getattr(quote, field) for field in QUOTE_FIELDS},
                ))
                inserted += 1
    return inserted


def _point_rows(curve_set):
    return [
        {
            "tenor_label": point.tenor_label,
            "tenor_years": point.tenor_years,
            "rate": point.rate,
            "source_series": point.source_series,
            "source_as_of": point.source_as_of,
        }
        for point in curve_set.points
    ]


def store_curve_set(curve_set):
    """Returns (created, changed) — points and raw rewrite only when the set changed."""
    now = utcnow()
    with session_scope() as session:
        row = (
            session.query(MarketDataCurve)
            .filter_by(
                provider=curve_set.provider,
                curve_name=curve_set.curve_name,
                as_of_date=curve_set.as_of_date,
            )
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            curve_id = uuid.uuid4()
            session.add(MarketDataCurve(
                curve_id=curve_id,
                provider=curve_set.provider,
                curve_name=curve_set.curve_name,
                curve_type=curve_set.curve_type,
                currency=curve_set.currency,
                index_tenor=curve_set.index_tenor,
                as_of_date=curve_set.as_of_date,
                received_at=curve_set.received_at,
                created_at=now,
                raw_payload=curve_set.raw_payload,
            ))
            session.flush()
            for point in _point_rows(curve_set):
                session.add(MarketDataCurvePoint(
                    curve_point_id=uuid.uuid4(), curve_id=curve_id,
                    created_at=now, **point,
                ))
            return True, True
        stored = [
            {field: getattr(point, field) for field in CURVE_POINT_FIELDS}
            for point in (
                session.query(MarketDataCurvePoint)
                .filter_by(curve_id=row.curve_id)
                .order_by(MarketDataCurvePoint.tenor_years)
                .all()
            )
        ]
        changed = stored != _point_rows(curve_set)
        row.received_at = curve_set.received_at
        if changed:
            row.curve_type = curve_set.curve_type
            row.currency = curve_set.currency
            row.index_tenor = curve_set.index_tenor
            row.raw_payload = curve_set.raw_payload
            session.query(MarketDataCurvePoint).filter_by(
                curve_id=row.curve_id
            ).delete(synchronize_session=False)
            for point in _point_rows(curve_set):
                session.add(MarketDataCurvePoint(
                    curve_point_id=uuid.uuid4(), curve_id=row.curve_id,
                    created_at=now, **point,
                ))
        return False, changed


def latest_curve_sets(provider=None, include_raw=False):
    with session_scope() as session:
        curves = (
            session.query(MarketDataCurve)
            .order_by(
                MarketDataCurve.provider,
                MarketDataCurve.curve_name,
                MarketDataCurve.as_of_date.desc(),
            )
            .all()
        )
        latest = {}
        for row in curves:
            key = (row.provider, row.curve_name)
            if key in latest:
                continue
            if provider is not None and row.provider != provider:
                continue
            latest[key] = {
                "curve_id": row.curve_id,
                "provider": row.provider,
                "curve_name": row.curve_name,
                "curve_type": row.curve_type,
                "currency": row.currency,
                "index_tenor": row.index_tenor,
                "as_of_date": row.as_of_date,
                "received_at": row.received_at,
                **({"raw_payload": row.raw_payload} if include_raw else {}),
            }
        for entry in latest.values():
            points = (
                session.query(MarketDataCurvePoint)
                .filter_by(curve_id=entry.pop("curve_id"))
                .order_by(MarketDataCurvePoint.tenor_years)
                .all()
            )
            entry["points"] = [
                {field: getattr(point, field) for field in CURVE_POINT_FIELDS}
                for point in points
            ]
        return sorted(latest.values(), key=lambda entry: entry["curve_name"])


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
    reference = reference_set.reference_board_symbols()
    with session_scope() as session:
        rows = session.query(
            MarketDataSpotPrice.market_data_id,
            MarketDataSpotPrice.provider,
            MarketDataSpotPrice.symbol,
        ).all()
        stray = [
            market_data_id
            for market_data_id, provider, symbol in rows
            if (
                symbol not in reference[provider]
                if provider in reference
                else symbol not in active or not active[symbol].serves(provider)
            )
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
