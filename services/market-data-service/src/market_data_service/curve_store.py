import uuid

from sqlalchemy.exc import IntegrityError

from desk_domain.curves import CURVE_CATALOG
from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from desk_domain.models import MarketDataCurve, MarketDataCurvePoint

CURVE_POINT_FIELDS = (
    "tenor_label",
    "tenor_years",
    "rate",
    "source_series",
    "source_as_of",
)


def prune_retired_curve_sets():
    with session_scope() as session:
        return (
            session.query(MarketDataCurve)
            .filter(MarketDataCurve.curve_name.notin_(tuple(CURVE_CATALOG)))
            .delete(synchronize_session=False)
        )


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
    """Returns (created, changed, accepted); older revisions are ignored."""
    try:
        return _store_curve_set(curve_set)
    except IntegrityError:
        # Two first fetches can race before there is a curve row to lock.
        return _store_curve_set(curve_set)


def _store_curve_set(curve_set):
    now = utcnow()
    with session_scope() as session:
        latest = (
            session.query(MarketDataCurve)
            .filter_by(
                provider=curve_set.provider,
                curve_name=curve_set.curve_name,
            )
            .order_by(MarketDataCurve.as_of_date.desc())
            .with_for_update()
            .first()
        )
        if latest is not None and (
            latest.as_of_date > curve_set.as_of_date
            or (
                latest.as_of_date == curve_set.as_of_date
                and latest.received_at > curve_set.received_at
            )
        ):
            return False, False, False
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
                curve_basis=curve_set.curve_basis,
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
            return True, True, True
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
        row.curve_basis = curve_set.curve_basis
        row.currency = curve_set.currency
        row.index_tenor = curve_set.index_tenor
        row.raw_payload = curve_set.raw_payload
        if changed:
            session.query(MarketDataCurvePoint).filter_by(
                curve_id=row.curve_id
            ).delete(synchronize_session=False)
            for point in _point_rows(curve_set):
                session.add(MarketDataCurvePoint(
                    curve_point_id=uuid.uuid4(), curve_id=row.curve_id,
                    created_at=now, **point,
                ))
        return False, changed, True


def _curve_entry(session, row, include_raw=False):
    entry = {
        "provider": row.provider,
        "curve_name": row.curve_name,
        "curve_basis": row.curve_basis,
        "currency": row.currency,
        "index_tenor": row.index_tenor,
        "as_of_date": row.as_of_date,
        "received_at": row.received_at,
        **({"raw_payload": row.raw_payload} if include_raw else {}),
    }
    points = (
        session.query(MarketDataCurvePoint)
        .filter_by(curve_id=row.curve_id)
        .order_by(MarketDataCurvePoint.tenor_years)
        .all()
    )
    entry["points"] = [
        {field: getattr(point, field) for field in CURVE_POINT_FIELDS}
        for point in points
    ]
    return entry


def curve_revision(provider, curve_name, as_of_date, include_raw=False):
    with session_scope() as session:
        row = (
            session.query(MarketDataCurve)
            .filter_by(
                provider=provider,
                curve_name=curve_name,
                as_of_date=as_of_date,
            )
            .one_or_none()
        )
        return None if row is None else _curve_entry(session, row, include_raw)


def latest_curve_sets(provider=None, include_raw=False):
    with session_scope() as session:
        curves = (
            session.query(MarketDataCurve)
            .filter(MarketDataCurve.curve_name.in_(tuple(CURVE_CATALOG)))
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
            latest[key] = _curve_entry(session, row, include_raw)
        return sorted(latest.values(), key=lambda entry: entry["curve_name"])


def latest_curve_set(provider, curve_name, include_raw=False):
    return next(
        (
            entry
            for entry in latest_curve_sets(provider, include_raw=include_raw)
            if entry["curve_name"] == curve_name
        ),
        None,
    )
