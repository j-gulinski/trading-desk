import uuid

from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert

from desk_domain.models import Instrument, Trade, WatchlistItem
from desk_domain.symbols import watched_providers
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from desk_runtime.functions import utcnow


def lock_instrument(session, symbol):
    return (
        session.query(Instrument).filter(Instrument.symbol == symbol)
        .with_for_update(of=Instrument).populate_existing().one_or_none()
    )


def ensure_instrument(session, symbol, asset_class, currency, *, name=None,
                      market=None, terms=None, underlying_id=None):
    session.execute(insert(Instrument).values(
        instrument_id=uuid.uuid4(), symbol=symbol, asset_class=asset_class,
        currency=currency, name=name, market=market, terms=terms or {},
        underlying_instrument_id=underlying_id, created_at=utcnow(),
    ).on_conflict_do_nothing(index_elements=[Instrument.symbol]))
    instrument = lock_instrument(session, symbol)
    different_market = market is not None and instrument.market is not None and market != instrument.market
    if (instrument.asset_class != asset_class or instrument.currency != currency
            or different_market or instrument.terms != (terms or {})
            or instrument.underlying_instrument_id != underlying_id):
        raise ValueError(f"{symbol} already identifies a different instrument")
    if instrument.retired_at is not None:
        raise ValueError(f"{symbol} is retired")
    return instrument


def require_watched_source(session, instrument, provider):
    if instrument is None or instrument.retired_at is not None:
        raise ValueError("instrument is missing or retired")
    membership = session.get(WatchlistItem, instrument.instrument_id, populate_existing=True)
    if membership is None or provider not in watched_providers(
        instrument.asset_class, membership.providers,
    ):
        raise ValueError(f"{instrument.symbol} is not watched on {provider}")


def active_source_dependency(session, instrument_id, providers):
    return (
        session.query(Trade.trade_id)
        .join(Instrument, Trade.instrument_id == Instrument.instrument_id)
        .filter(
            Trade.status == "ACTIVE",
            or_(Trade.instrument_id == instrument_id,
                Instrument.underlying_instrument_id == instrument_id),
            func.coalesce(Trade.market_data_provider, DEFAULT_QUOTE_PROVIDER).in_(providers),
        )
        .first() is not None
    )
