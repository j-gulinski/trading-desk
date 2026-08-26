from shared.curves import (
    curve_metadata,
    curve_stale_after_days,
    curve_trade_roles,
    curve_trade_uses,
)
from shared.db import session_scope
from shared.functions import utcnow
from shared.models import MarketDataCurve, MarketDataCurvePoint


def _latest_rows(session):
    rows = (
        session.query(
            MarketDataCurve.curve_id,
            MarketDataCurve.provider,
            MarketDataCurve.curve_name,
            MarketDataCurve.curve_basis,
            MarketDataCurve.currency,
            MarketDataCurve.index_tenor,
            MarketDataCurve.as_of_date,
            MarketDataCurve.received_at,
        )
        .order_by(MarketDataCurve.curve_name, MarketDataCurve.as_of_date.desc())
        .all()
    )
    latest = {}
    for (
        curve_id, provider, name, curve_basis, currency, index_tenor, as_of, received_at
    ) in rows:
        if name in latest:
            continue
        age_days = max(0, (utcnow().date() - as_of).days)
        stale_after_days = curve_stale_after_days(name)
        trade_uses = curve_trade_uses(name)
        latest[name] = {
            "curve_id": curve_id,
            "provider": provider,
            "curve_name": name,
            "curve_basis": curve_basis,
            "roles": list(curve_trade_roles(name)),
            "uses": list(trade_uses),
            **curve_metadata(name),
            "currency": currency,
            "index_tenor": index_tenor,
            "as_of_date": str(as_of),
            "received_at": received_at.isoformat(),
            "age_days": age_days,
            "stale_after_days": stale_after_days,
            "stale": stale_after_days is not None and age_days > stale_after_days,
        }
    return latest


def latest_curve_sets(session=None):
    """Metadata of the newest stored set per curve name, JSON-safe."""
    if session is None:
        with session_scope() as owned:
            latest = _latest_rows(owned)
    else:
        latest = _latest_rows(session)
    return [
        {key: value for key, value in entry.items() if key != "curve_id"}
        for entry in sorted(latest.values(), key=lambda entry: entry["curve_name"])
    ]


def load_curve(curve_name, session=None):
    """The newest stored set with pricing arrays (tenors in years, rates as decimal
    fractions of the stored percent values), or None."""

    def read(active_session):
        entry = _latest_rows(active_session).get(curve_name)
        if entry is None:
            return None
        points = (
            active_session.query(
                MarketDataCurvePoint.tenor_years, MarketDataCurvePoint.rate
            )
            .filter_by(curve_id=entry["curve_id"])
            .order_by(MarketDataCurvePoint.tenor_years)
            .all()
        )
        return {
            **{key: value for key, value in entry.items() if key != "curve_id"},
            "tenors": [float(tenor) for tenor, _ in points],
            "rates": [float(rate) / 100.0 for _, rate in points],
        }

    if session is None:
        with session_scope() as owned:
            return read(owned)
    return read(session)
