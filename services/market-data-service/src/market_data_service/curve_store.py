import uuid

from desk_domain.audit import write_audit
from desk_domain.curve_registry import latest_revisions
from desk_domain.curves import CURVE_CATALOG
from desk_domain.models import MarketDataCurve, MarketDataCurvePoint
from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from market_data_service.config import SERVICE_NAME

CURVE_FIELDS = (
    "provider",
    "curve_name",
    "curve_basis",
    "currency",
    "index_tenor",
    "as_of_date",
    "received_at",
)
POINT_FIELDS = (
    "tenor_label",
    "tenor_years",
    "rate",
    "source_series",
    "source_as_of",
)


def _point_dicts(points):
    return [{field: getattr(point, field) for field in POINT_FIELDS} for point in points]


def curve_entry(curve, points):
    """A fetched curve set or stored curve row, with its points, as a plain dict."""
    return {
        **{field: getattr(curve, field) for field in CURVE_FIELDS},
        "points": _point_dicts(points),
    }


def prune_retired_curve_sets():
    with session_scope() as session:
        return (
            session.query(MarketDataCurve)
            .filter(MarketDataCurve.curve_name.notin_(tuple(CURVE_CATALOG)))
            .delete(synchronize_session=False)
        )


def store_curve_set(curve_set):
    """Stores a curve unless a newer one is stored; returns (accepted, newest as-of date)."""
    now = utcnow()
    points = _point_dicts(curve_set.points)
    with session_scope() as session:
        latest = (
            session.query(MarketDataCurve)
            .filter_by(provider=curve_set.provider, curve_name=curve_set.curve_name)
            .order_by(MarketDataCurve.as_of_date.desc())
            .with_for_update()
            .first()
        )
        if latest is not None and (
            (latest.as_of_date, latest.received_at) > (curve_set.as_of_date, curve_set.received_at)
        ):
            return False, latest.as_of_date
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
        created = row is None
        if created:
            row = MarketDataCurve(curve_id=uuid.uuid4(), created_at=now)
            session.add(row)
            changed = True
        else:
            stored = (
                session.query(MarketDataCurvePoint)
                .filter_by(curve_id=row.curve_id)
                .order_by(MarketDataCurvePoint.tenor_years)
                .all()
            )
            changed = _point_dicts(stored) != points
            if changed:
                session.query(MarketDataCurvePoint).filter_by(
                    curve_id=row.curve_id
                ).delete(synchronize_session=False)
        for field in CURVE_FIELDS:
            setattr(row, field, getattr(curve_set, field))
        row.raw_payload = curve_set.raw_payload
        session.flush()
        if changed:
            session.add_all(
                MarketDataCurvePoint(
                    curve_point_id=uuid.uuid4(), curve_id=row.curve_id, created_at=now, **point,
                )
                for point in points
            )
            write_audit(
                SERVICE_NAME,
                "CURVE_SET_WRITTEN",
                f"{curve_set.provider} {'published' if created else 'revised'} "
                f"{curve_set.curve_name} as of {curve_set.as_of_date}",
                entity_type="CURVE",
                entity_id=f"{curve_set.provider}:{curve_set.curve_name}",
                payload={
                    "provider": curve_set.provider,
                    "curve_name": curve_set.curve_name,
                    "curve_basis": curve_set.curve_basis,
                    "currency": curve_set.currency,
                    "as_of_date": str(curve_set.as_of_date),
                    "points": len(points),
                },
                session=session,
            )
        return True, curve_set.as_of_date


def _entries(session, curves, include_raw):
    ids = [curve.curve_id for curve in curves]
    points = {}
    for point in (
        session.query(MarketDataCurvePoint)
        .filter(MarketDataCurvePoint.curve_id.in_(ids))
        .order_by(MarketDataCurvePoint.tenor_years)
    ):
        points.setdefault(point.curve_id, []).append(point)
    raw_payloads = dict(
        session.query(MarketDataCurve.curve_id, MarketDataCurve.raw_payload)
        .filter(MarketDataCurve.curve_id.in_(ids))
    ) if include_raw else {}
    entries = []
    for curve in curves:
        entry = curve_entry(curve, points.get(curve.curve_id, ()))
        if include_raw:
            entry["raw_payload"] = raw_payloads[curve.curve_id]
        entries.append(entry)
    return entries


def curve_revision(provider, curve_name, as_of_date, include_raw=False):
    with session_scope() as session:
        row = (
            session.query(MarketDataCurve)
            .filter_by(provider=provider, curve_name=curve_name, as_of_date=as_of_date)
            .one_or_none()
        )
        return None if row is None else _entries(session, [row], include_raw)[0]


def latest_curve_sets(provider=None, include_raw=False):
    """The newest stored revision of every catalog curve, ordered by curve name."""
    with session_scope() as session:
        revisions = [
            revision for revision in latest_revisions(session)
            if revision.curve_name in CURVE_CATALOG and provider in (None, revision.provider)
        ]
        return _entries(session, revisions, include_raw)
