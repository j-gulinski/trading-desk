import uuid
from datetime import datetime, time as day_time, timezone
from decimal import Decimal

from trade_action_service import market_state, repository
from trade_action_service.config import TRADE_PRICE_TOLERANCE_PCT
from desk_domain.contract_data import trade_terms
from desk_domain.active_set import load_active_set
from desk_domain.curve_registry import load_curve
from desk_domain.freshness import FreshnessState
from desk_domain.instruments import instrument_for, instrument_type_for
from desk_domain.trade_rules import validate_position, validate_price
from desk_pricing.provenance import pricing_provenance
from desk_domain.providers import QUOTE_PROVIDERS, supports_quotes
from desk_domain.symbols import is_valid_symbol, model_contract_symbol
from desk_domain.term_schemas import checked_terms


CLOSING_SIDE = {"BUY": "SELL", "SELL": "BUY"}


def parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _moved_error(executed, seen, instrument, subject):
    notional = instrument.deviation_notional
    scale = notional if notional is not None else abs(seen)
    if not scale:
        return None
    deviation = abs(executed - seen) / scale * 100
    if deviation <= Decimal(str(TRADE_PRICE_TOLERANCE_PCT)):
        return None
    basis = f" of {'notional' if notional is not None else 'its value'}" if subject == "model value" else ""
    return (
        f"{subject} moved {deviation:.2f}%{basis} from the {seen} shown to you "
        f"(limit {TRADE_PRICE_TOLERANCE_PCT}%)"
    )


def _resolve_terms(session, intent, instrument_type, active):
    asset_class = instrument_type.asset_class
    custom = intent.get("terms")
    if custom is not None:
        return checked_terms(session, asset_class, custom)
    if instrument_type.fields:
        raise ValueError(f"{asset_class} requires instrument terms")
    entry = active.get(intent.get("symbol"))
    if entry is None or entry.asset_class != asset_class or not entry.tradeable:
        raise ValueError("symbol is not tradeable for this asset class")
    return {"asset_class": entry.asset_class, "currency": entry.currency}


def _resolve_provider(symbol, provider, active):
    entry = active.get(symbol)
    if entry is None or not entry.tradeable:
        raise ValueError(f"{symbol} is not tradeable")
    if not provider:
        raise ValueError(f"market data provider is required for {entry.asset_class}")
    if provider not in QUOTE_PROVIDERS:
        raise ValueError(f"unknown market data provider {provider}")
    if not supports_quotes(provider, entry.asset_class):
        raise ValueError(f"{provider} cannot quote {entry.asset_class}")
    if not entry.serves_open(provider):
        raise ValueError(f"{symbol} is not watched on {provider}")
    return provider


def _quote_execution(session, instrument, symbol, provider, side, seen, allow_stale=False):
    quote, state = market_state.current_quote(session, provider, symbol)
    if state is FreshnessState.MISSING:
        raise ValueError(f"{provider} has no current quote for {symbol}")
    if not allow_stale and state is FreshnessState.STALE:
        raise ValueError(f"the {provider} quote for {symbol} is stale")
    if not allow_stale and state is FreshnessState.EOD:
        raise ValueError(f"the {provider} quote for {symbol} is an end-of-day close")
    price = quote.price_for(side)
    if price is None or price <= 0:
        raise ValueError(f"{provider} has no usable price for {symbol}")
    error = _moved_error(price, seen, instrument, "price")
    if error:
        raise ValueError(error)
    return quote, price


def _as_of_timestamp(as_of_text):
    return datetime.combine(
        datetime.strptime(as_of_text, "%Y-%m-%d").date(),
        day_time(0, 0),
        tzinfo=timezone.utc,
    )


def _model_execution(session, instrument, provider, seen, *, allow_stale=False, stale_ack=False):
    curve = None
    if instrument.uses_curve():
        name = instrument.discount_curve
        curve = load_curve(name, session=session)
        if curve is None:
            raise ValueError(f"no stored {name} curve set is available yet")
        if curve.get("stale") and not allow_stale and not stale_ack:
            raise ValueError(f"stale curve acknowledgement is required for {name}")
    underlying = instrument.quote_symbol
    underlying_quote = None
    if underlying:
        underlying_quote, state = market_state.current_quote(session, provider, underlying)
        if state is FreshnessState.MISSING:
            raise ValueError(f"{provider} has no current quote for {underlying}")
        if state is FreshnessState.STALE and not allow_stale:
            raise ValueError(f"the {provider} quote for {underlying} is stale")
        if state is FreshnessState.EOD and not allow_stale:
            raise ValueError(f"the {provider} quote for {underlying} is an end-of-day close")
    result = instrument.price({
        "curve": curve, "spot": {"mid": underlying_quote.mid} if underlying_quote else {},
    })
    price = result["price"] if result else None
    if price is None or not price.is_finite():
        raise ValueError("the supplied model inputs did not produce a finite value")
    error = _moved_error(price, seen, instrument, "model value")
    if error:
        raise ValueError(error)
    if underlying_quote is not None:
        quote_time = underlying_quote.provider_timestamp
        quote_state = underlying_quote.state
        snapshot_id = underlying_quote.snapshot_id
    else:
        quote_time = _as_of_timestamp(curve["as_of_date"])
        quote_state = FreshnessState.LIVE
        snapshot_id = None
    quote = market_state.ModelQuote(
        instrument.currency, quote_state,
        provider_timestamp=quote_time,
        snapshot_id=snapshot_id,
    )
    provenance = {"pricing_provenance": pricing_provenance(
        instrument.model, curve, getattr(instrument, "maturity_years", None),
    )}
    if curve is not None:
        provenance["discount_curve_provider"] = curve["provider"]
        provenance["discount_curve_as_of"] = curve["as_of_date"]
        if curve.get("stale") and not allow_stale:
            provenance["stale_curve_acknowledged"] = [instrument.discount_curve]
    return price, quote, provenance


def validate_open(session, intent):
    """Return the execution plan for an open, or raise ValueError with the reason."""
    book_id = parse_uuid(intent.get("book_id"))
    book = repository.lock_active_book(session, book_id) if book_id else None
    if book is None:
        raise ValueError("unknown or inactive book")
    asset_class = intent.get("asset_class")
    if book.expected_asset_class != asset_class:
        raise ValueError(f"{book.name} takes {book.expected_asset_class}, not {asset_class}")
    instrument_type = instrument_type_for(asset_class)
    active = load_active_set(session)
    terms = _resolve_terms(session, intent, instrument_type, active)
    instrument = instrument_for(asset_class, intent.get("symbol"), terms)
    _, seen = validate_position(instrument, intent.get("side"), intent.get("quantity"),
                                intent.get("client_seen_price"), "client_seen_price")
    if instrument.symbol_prefix is not None:
        intent["symbol"] = model_contract_symbol(instrument, intent.get("trade_id"))
        if not is_valid_symbol(intent["symbol"]):
            raise ValueError("could not assign a contract reference")
        instrument.symbol = intent["symbol"]
        provider = None
        if instrument.needs_quote:
            provider = _resolve_provider(
                instrument.quote_symbol, intent.get("market_data_provider"), active,
            )
        price, quote, provenance = _model_execution(
            session, instrument, provider, seen,
            stale_ack=intent.get("stale_curve_acknowledged") is True,
        )
        instrument.extras.update(provenance)
    else:
        provider = _resolve_provider(intent.get("symbol"), intent.get("market_data_provider"), active)
        quote, price = _quote_execution(
            session, instrument, intent.get("symbol"), provider, intent.get("side"), seen,
        )
    return {"instrument": instrument, "provider": provider, "quote": quote, "price": price}


def validate_close(session, intent):
    """Return the execution plan for a close, or raise ValueError with the reason."""
    trade_id = parse_uuid(intent.get("trade_id"))
    trade = repository.active_trade(session, trade_id) if trade_id else None
    if trade is None:
        raise ValueError("trade is not open")
    instrument = instrument_for(trade.instrument.asset_class, trade.instrument.symbol,
                                trade_terms(trade))
    seen = validate_price(instrument, intent.get("client_seen_price"), "client_seen_price")
    provider = trade.market_data_provider
    if instrument.symbol_prefix is not None:
        price, quote, provenance = _model_execution(
            session, instrument, provider, seen, allow_stale=True,
        )
        return {"trade": trade, "provider": provider, "quote": quote, "price": price,
                "close_provenance": {f"close_{key}": value for key, value in provenance.items()}}
    quote, price = _quote_execution(
        session, instrument, trade.instrument.symbol, provider,
        CLOSING_SIDE[trade.side], seen, allow_stale=True,
    )
    return {"trade": trade, "provider": provider, "quote": quote, "price": price}


def validate_reassign(session, intent):
    """Return (source, target) books for a reassign, or raise ValueError with the reason."""
    source_id = parse_uuid(intent.get("book_id"))
    target_id = parse_uuid(intent.get("target_book_id"))
    source = repository.get_book(session, source_id) if source_id else None
    target = repository.lock_active_book(session, target_id) if target_id else None
    if source is None or target is None or source_id == target_id:
        raise ValueError("unknown or same book")
    if source.expected_asset_class != target.expected_asset_class:
        raise ValueError("asset class mismatch")
    return source, target
