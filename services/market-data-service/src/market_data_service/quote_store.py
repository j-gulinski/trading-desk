import uuid

from sqlalchemy.exc import IntegrityError

from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from desk_domain.models import MarketDataSnapshot, MarketDataSpotPrice
from desk_domain.quotes import quote_market, quote_name

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
BOARD_EXTRA_FIELDS = ("previous_close",)
CLASSIFIER_FIELDS = ("stale_after_seconds", "closed_stale_after_seconds", "market_open")


def _store_quote(quote, classifier):
    with session_scope() as session:
        row = (
            session.query(MarketDataSpotPrice)
            .filter_by(provider=quote.provider, symbol=quote.symbol)
            .with_for_update()
            .one_or_none()
        )
        if row is not None:
            older_provider_clock = (
                row.provider_timestamp is not None
                and (
                    quote.provider_timestamp is None
                    or quote.provider_timestamp < row.provider_timestamp
                )
            )
            older_receive_clock = (
                quote.provider_timestamp == row.provider_timestamp
                and row.received_at is not None
                and quote.received_at <= row.received_at
            )
            if older_provider_clock or older_receive_clock:
                return False, False, False
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
        for field in QUOTE_FIELDS + BOARD_EXTRA_FIELDS:
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
        return changed, created, True


def store_quote(quote, classifier):
    try:
        return _store_quote(quote, classifier)
    except IntegrityError:
        # Two first polls can race before there is a board row to lock.
        return _store_quote(quote, classifier)


def board_rows():
    with session_scope() as session:
        rows = (
            session.query(MarketDataSpotPrice, MarketDataSnapshot.raw_payload)
            .outerjoin(
                MarketDataSnapshot,
                MarketDataSnapshot.snapshot_id == MarketDataSpotPrice.latest_snapshot_id,
            )
            .order_by(MarketDataSpotPrice.provider, MarketDataSpotPrice.symbol)
            .all()
        )
        return [
            {
                **{field: getattr(row, field) for field in QUOTE_FIELDS + BOARD_EXTRA_FIELDS},
                **{field: getattr(row, field) for field in CLASSIFIER_FIELDS},
                "latest_snapshot_id": row.latest_snapshot_id,
                "name": quote_name(row.symbol, raw_payload),
                "market": quote_market(row.symbol, row.asset_class, raw_payload),
            }
            for row, raw_payload in rows
        ]


def quote_history(provider, symbol, limit, include_raw=False):
    with session_scope() as session:
        rows = (
            session.query(MarketDataSnapshot)
            .filter_by(provider=provider, symbol=symbol)
            .order_by(
                MarketDataSnapshot.provider_timestamp.desc(),
                MarketDataSnapshot.received_at.desc(),
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


def quote_clocks(provider, symbol):
    with session_scope() as session:
        row = (
            session.query(
                MarketDataSpotPrice.provider_timestamp,
                MarketDataSpotPrice.received_at,
            )
            .filter_by(provider=provider, symbol=symbol)
            .one_or_none()
        )
        return tuple(row) if row is not None else (None, None)


def delete_board_rows(symbol, providers=None):
    with session_scope() as session:
        query = session.query(MarketDataSpotPrice).filter_by(symbol=symbol)
        if providers is not None:
            query = query.filter(MarketDataSpotPrice.provider.in_(list(providers)))
        return query.delete(synchronize_session=False)
