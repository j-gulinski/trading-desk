from decimal import Decimal

from shared.freshness import FreshnessState, classify
from shared.functions import utcnow
from shared.models import MarketDataSnapshot, MarketDataSpotPrice
from shared.quotes import PriceBasis


class Quote:
    def __init__(self, row, state, snapshot_id=None):
        self.provider = row.provider
        self.symbol = row.symbol
        self.currency = row.currency
        self.bid = row.bid
        self.ask = row.ask
        self.mid = row.mid
        self.price_basis = row.price_basis
        self.provider_timestamp = row.provider_timestamp
        self.snapshot_id = snapshot_id
        self.state = state

    def price_for(self, side):
        quoted = self.ask if side == "BUY" else self.bid
        return quoted if quoted is not None else self.mid

    def executed_basis(self, side):
        quoted = self.ask if side == "BUY" else self.bid
        return PriceBasis.BID_ASK.value if quoted is not None else self.price_basis


def current_quote(session, provider, symbol):
    row = (
        session.query(MarketDataSpotPrice)
        .filter_by(provider=provider, symbol=symbol)
        .one_or_none()
    )
    if row is None:
        return None, FreshnessState.MISSING
    state = classify(
        True,
        row.provider_timestamp,
        row.received_at,
        utcnow(),
        row.stale_after_seconds,
        market_open=row.market_open,
        closed_stale_after_seconds=row.closed_stale_after_seconds,
    )
    snapshot = (
        session.get(MarketDataSnapshot, row.latest_snapshot_id)
        if row.latest_snapshot_id else None
    )
    snapshot_id = (
        snapshot.snapshot_id
        if snapshot is not None and snapshot.received_at == row.received_at
        else None
    )
    return Quote(row, state, snapshot_id), state


class ModelQuote:
    """Quote-shaped record for a model-priced (curve) execution — what insert_trade
    and the audit payload read."""

    def __init__(self, currency, state, provider_timestamp=None, snapshot_id=None):
        self.currency = currency
        self.state = state
        self.provider_timestamp = provider_timestamp
        self.snapshot_id = snapshot_id

    def executed_basis(self, side):
        return "MODEL_PV"


def model_deviation_percent(executed, seen):
    if seen in (None, "") or executed is None or executed == 0:
        return None
    try:
        seen_price = Decimal(str(seen))
    except (ArithmeticError, ValueError):
        return None
    return abs(executed - seen_price) / abs(executed) * 100


def is_parseable_price(seen):
    if seen in (None, ""):
        return True
    try:
        Decimal(str(seen))
    except (ArithmeticError, ValueError, TypeError):
        return False
    return True


def deviation_percent(executed, seen):
    if seen in (None, "") or executed in (None, 0):
        return None
    try:
        seen_price = Decimal(str(seen))
    except (ArithmeticError, ValueError):
        return None
    if seen_price <= 0:
        return None
    return abs(executed - seen_price) / executed * 100
