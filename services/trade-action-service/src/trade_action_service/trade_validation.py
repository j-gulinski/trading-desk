import uuid
from datetime import datetime, time as day_time, timezone
from decimal import Decimal

from trade_action_service import market_state, repository
from trade_action_service.config import QUOTE_PROVIDER_CHOICES, TRADE_PRICE_TOLERANCE_PCT
from desk_domain.contract_data import trade_terms
from desk_domain.active_set import load_active_set
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from desk_domain.curve_registry import latest_curve_sets, load_curve
from desk_domain.freshness import FreshnessState
from desk_domain.instruments import instrument_for
from desk_domain.trade_rules import validate_position
from desk_pricing.provenance import pricing_provenance
from desk_domain.providers import supports_quotes
from desk_domain.symbols import is_valid_symbol, model_contract_symbol, watchlist_spot_catalog
from desk_domain.term_schemas import validate_terms


CLOSING_SIDE = {"BUY": "SELL", "SELL": "BUY"}


def parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _resolve_terms(session, intent, instrument, active, curves=()):
    asset_class = instrument.asset_class
    custom = intent.get("terms")
    if custom is not None:
        return validate_terms(asset_class, custom, watchlist_spot_catalog(session), curves)
    if instrument.needs_curve:
        return None, f"{asset_class} requires instrument terms"
    entry = active.get(intent.get("symbol"))
    if entry is None or entry.asset_class != asset_class or not entry.tradeable:
        return None, "symbol is not tradeable for this asset class"
    return {"asset_class": entry.asset_class, "currency": entry.currency}, None


def _resolve_provider(symbol, provider, active):
    entry = active.get(symbol)
    if entry is None or not entry.tradeable:
        return None, f"{symbol} is not tradeable"
    if not provider:
        return None, f"market data provider is required for {entry.asset_class}"
    if provider not in QUOTE_PROVIDER_CHOICES:
        return None, f"unknown market data provider {provider}"
    if not supports_quotes(provider, entry.asset_class):
        return None, f"{provider} cannot quote {entry.asset_class}"
    if not entry.serves_open(provider):
        return None, f"{symbol} is not watched on {provider}"
    return provider, None


def _resolve_execution(session, intent, provider, side, allow_stale=False):
    symbol = intent.get("symbol")
    quote, state = market_state.current_quote(session, provider, symbol)
    if state is FreshnessState.MISSING:
        return None, None, f"{provider} has no current quote for {symbol}"
    if not allow_stale and state is FreshnessState.STALE:
        return quote, None, f"the {provider} quote for {symbol} is stale"
    price = quote.price_for(side)
    if price is None or price <= 0:
        return quote, None, f"{provider} has no usable price for {symbol}"
    deviation = market_state.deviation_percent(price, intent.get("client_seen_price"))
    if deviation is not None and deviation > TRADE_PRICE_TOLERANCE_PCT:
        return quote, None, (
            f"price moved {deviation:.2f}% from the {intent.get('client_seen_price')} "
            f"shown to you (limit {TRADE_PRICE_TOLERANCE_PCT}%)"
        )
    return quote, price, None


def _as_of_timestamp(as_of_text):
    return datetime.combine(
        datetime.strptime(as_of_text, "%Y-%m-%d").date(),
        day_time(0, 0),
        tzinfo=timezone.utc,
    )


def _model_deviation_error(instrument, price, seen):
    if price is None or not price.is_finite():
        return "the supplied model inputs did not produce a finite value"
    if seen in (None, ""):
        return None
    try:
        seen_price = Decimal(str(seen))
    except (ArithmeticError, ValueError, TypeError):
        return "client_seen_price must be a finite number"
    if not seen_price.is_finite():
        return "client_seen_price must be a finite number"
    notional = instrument.deviation_notional
    scale = notional if notional is not None else abs(seen_price)
    if not scale:
        return None
    deviation = abs(price - seen_price) / scale * 100
    if deviation > Decimal(str(TRADE_PRICE_TOLERANCE_PCT)):
        return (
            f"model value moved {deviation:.2f}% of "
            f"{'notional' if notional is not None else 'its value'} from the "
            f"{seen} shown to you (limit {TRADE_PRICE_TOLERANCE_PCT}%)"
        )
    return None


def _curve_execution(session, instrument, provider, seen, *, allow_stale=False, stale_ack=False):
    terms = instrument.terms
    name = terms["discount_curve"]
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
    result = instrument.price({
        "curve": curve, "spot": {"mid": underlying_quote.mid} if underlying_quote else {},
    })
    price = result["price"] if result else None
    error = _model_deviation_error(instrument, price, seen)
    if error:
        raise ValueError(error)
    quote = market_state.ModelQuote(
        terms["currency"], underlying_quote.state if underlying_quote else FreshnessState.LIVE,
        provider_timestamp=(underlying_quote.provider_timestamp if underlying_quote
                            else _as_of_timestamp(curve["as_of_date"])),
        snapshot_id=underlying_quote.snapshot_id if underlying_quote else None,
    )
    projection = curve if terms.get("projection_curve") else None
    provenance = {"pricing_provenance": pricing_provenance(instrument.model, curve, projection)}
    for role in (("discount_curve", "projection_curve") if projection else ("discount_curve",)):
        provenance[f"{role}_provider"] = curve["provider"]
        provenance[f"{role}_as_of"] = curve["as_of_date"]
    if curve.get("stale") and not allow_stale:
        provenance["stale_curve_acknowledged"] = [name]
    return price, quote, provenance


def _validate_curve_open(session, intent, active, instrument):
    provider = None
    if instrument.needs_quote:
        provider, error = _resolve_provider(
            instrument.quote_symbol, intent.get("market_data_provider"), active,
        )
        if error:
            return None, error
    try:
        price, quote, provenance = _curve_execution(
            session, instrument, provider, intent.get("client_seen_price"),
            stale_ack=intent.get("stale_curve_acknowledged") is True,
        )
    except (ValueError, ArithmeticError) as exc:
        return None, str(exc)
    instrument.terms.update(provenance)
    return {"instrument": instrument, "provider": provider, "quote": quote, "price": price}, None


def validate_open(session, intent):
    book_id = parse_uuid(intent.get("book_id"))
    book = repository.get_active_book(session, book_id) if book_id else None
    if book is None:
        return None, "unknown or inactive book"
    if book.expected_asset_class != intent.get("asset_class"):
        return None, (
            f"{book.name} takes {book.expected_asset_class}, "
            f"not {intent.get('asset_class')}"
        )
    asset_class = intent.get("asset_class")
    try:
        instrument = instrument_for(asset_class, intent.get("symbol"))
    except ValueError as exc:
        return None, str(exc)
    active = load_active_set(session)
    curves = (
        latest_curve_sets(session)
        if instrument.needs_curve
        else ()
    )
    terms, term_error = _resolve_terms(session, intent, instrument, active, curves)
    if terms is None:
        return None, term_error
    instrument.terms = terms
    try:
        validate_position(instrument, intent.get("side"), intent.get("quantity"),
                          intent.get("client_seen_price"))
    except ValueError as exc:
        return None, str(exc)
    if instrument.symbol_prefix is not None:
        intent["symbol"] = model_contract_symbol(instrument, intent.get("trade_id"))
        if not is_valid_symbol(intent["symbol"]):
            return None, "could not assign a contract reference"
        instrument.symbol = intent["symbol"]
        return _validate_curve_open(session, intent, active, instrument)
    provider, provider_error = _resolve_provider(
        intent.get("symbol"), intent.get("market_data_provider"), active,
    )
    if provider_error is not None:
        return None, provider_error
    quote, price, execution_error = _resolve_execution(
        session, intent, provider, intent.get("side")
    )
    if execution_error is not None:
        return None, execution_error
    return {"instrument": instrument, "provider": provider, "quote": quote, "price": price}, None


def _validate_curve_close(session, intent, trade, instrument):
    provider = (trade.market_data_provider or DEFAULT_QUOTE_PROVIDER) if instrument.needs_quote else None
    try:
        price, quote, provenance = _curve_execution(
            session, instrument, provider, intent.get("client_seen_price"), allow_stale=True,
        )
    except (ValueError, ArithmeticError) as exc:
        return None, str(exc)
    return {"trade": trade, "provider": provider, "quote": quote, "price": price,
            "close_provenance": {f"close_{key}": value for key, value in provenance.items()}}, None


def validate_close(session, intent, require_seen=True):
    trade_id = parse_uuid(intent.get("trade_id"))
    trade = repository.active_trade(session, trade_id) if trade_id else None
    if trade is None:
        return None, "trade is not open"
    instrument = instrument_for(trade.instrument.asset_class, trade.instrument.symbol, trade_terms(trade))
    seen_price = intent.get("client_seen_price")
    if require_seen and not market_state.is_parseable_price(seen_price):
        return None, "client_seen_price must be a finite number"
    if (
        require_seen
        and not instrument.allows_negative_price
        and not market_state.is_positive_price(seen_price)
    ):
        return None, "client_seen_price must be greater than zero"
    if instrument.needs_curve:
        return _validate_curve_close(session, intent, trade, instrument)
    provider = trade.market_data_provider or DEFAULT_QUOTE_PROVIDER
    quote, price, error = _resolve_execution(
        session,
        {**intent, "symbol": trade.instrument.symbol},
        provider,
        CLOSING_SIDE.get(trade.side, "SELL"),
        allow_stale=True,
    )
    if error is not None:
        return None, error
    return {"trade": trade, "provider": provider, "quote": quote, "price": price}, None
