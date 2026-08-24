from shared.db import session_scope
from shared.models import MarketDataCurve, MarketDataCurvePoint


def _latest_rows(session):
    rows = (
        session.query(
            MarketDataCurve.curve_id,
            MarketDataCurve.provider,
            MarketDataCurve.curve_name,
            MarketDataCurve.curve_type,
            MarketDataCurve.currency,
            MarketDataCurve.index_tenor,
            MarketDataCurve.as_of_date,
        )
        .order_by(MarketDataCurve.curve_name, MarketDataCurve.as_of_date.desc())
        .all()
    )
    latest = {}
    for curve_id, provider, name, curve_type, currency, index_tenor, as_of in rows:
        if name in latest:
            continue
        latest[name] = {
            "curve_id": curve_id,
            "provider": provider,
            "curve_name": name,
            "curve_type": curve_type,
            "currency": currency,
            "index_tenor": index_tenor,
            "as_of_date": str(as_of),
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
