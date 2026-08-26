import math
import uuid
from datetime import datetime, time as day_time, timezone
from decimal import Decimal

from app import market_state, repository
from app.config import QUOTE_PROVIDER_CHOICES, TRADE_PRICE_TOLERANCE_PCT
from shared.active_set import load_active_set
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.curve_registry import latest_curve_sets, load_curve
from shared.freshness import FreshnessState
from shared.pricing.bond import bond_pv
from shared.pricing.european_option import european_option_pv
from shared.pricing.irs import irs_pv
from shared.providers import supports_quotes
from shared.symbols import (
    CURVE_PRICED_ASSET_CLASSES,
    SPOT_ASSET_CLASSES,
    TRADE_QUANTITY_MAX,
    TRADE_QUANTITY_MIN,
    WHOLE_QUANTITY_ASSET_CLASSES,
    is_valid_symbol,
    model_contract_symbol,
    watchlist_option_underlying_symbols,
    watchlist_spot_currencies,
)
from shared.term_schemas import DEFAULT_VOLATILITY, validate_terms


CLOSING_SIDE = {"BUY": "SELL", "SELL": "BUY"}


def parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _resolve_terms(session, intent, active, curves=()):
    asset_class = intent.get("asset_class")
    custom = intent.get("terms")
    if custom is not None:
        return validate_terms(
            asset_class,
            custom,
            watchlist_option_underlying_symbols(session),
            curves,
            watchlist_spot_currencies(session),
        )
    if asset_class in CURVE_PRICED_ASSET_CLASSES:
        return None, f"{asset_class} requires instrument terms"
    entry = active.get(intent.get("symbol"))
    if entry is None or entry.asset_class != asset_class or not entry.tradeable:
        return None, "symbol is not tradeable for this asset class"
    return {"asset_class": entry.asset_class, "currency": entry.currency}, None


def _resolve_provider(intent, active):
    asset_class = intent.get("asset_class")
    provider = intent.get("market_data_provider")
    symbol = intent.get("symbol")
    if asset_class not in SPOT_ASSET_CLASSES:
        return None, f"unsupported asset class {asset_class}"
    if not provider:
        return None, f"market data provider is required for {asset_class}"
    if provider not in QUOTE_PROVIDER_CHOICES:
        return None, f"unknown market data provider {provider}"
    if not supports_quotes(provider, asset_class):
        return None, f"{provider} cannot quote {asset_class}"
    entry = active.get(symbol)
    if entry is None or not entry.serves_open(provider):
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


def _load_terms_curves(terms):
    curves = {}
    for field in ("discount_curve", "projection_curve"):
        name = terms.get(field) or (
            terms.get("curve") if field == "discount_curve" else None
        )
        if name is None:
            continue
        curve = load_curve(name)
        if curve is None:
            return None, f"no stored {name} curve set is available yet"
        curves[field] = curve
    return curves, None


def _model_price(terms, curves, underlying_mid=None):
    discount = curves["discount_curve"]
    if terms["asset_class"] == "IRS":
        value = irs_pv(terms, discount, curves.get("projection_curve"))
    elif terms["asset_class"] == "BOND":
        value = bond_pv(terms, discount)
    else:
        value = european_option_pv(
            terms,
            underlying_mid,
            discount,
            terms.get("volatility", DEFAULT_VOLATILITY),
        )
    result = Decimal(str(value))
    return result if result.is_finite() else None


def _deviation_scale(terms, seen_price):
    if terms["asset_class"] == "IRS":
        return Decimal(str(terms["notional"]))
    return abs(seen_price)


def _model_deviation_error(terms, price, seen):
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
    scale = _deviation_scale(terms, seen_price)
    if not scale:
        return None
    deviation = abs(price - seen_price) / scale * 100
    if deviation > Decimal(str(TRADE_PRICE_TOLERANCE_PCT)):
        return (
            f"model value moved {deviation:.2f}% of "
            f"{'notional' if terms['asset_class'] == 'IRS' else 'its value'} from the "
            f"{seen} shown to you (limit {TRADE_PRICE_TOLERANCE_PCT}%)"
        )
    return None


def _freeze_curve_provenance(terms, curves):
    for field, curve in curves.items():
        terms[f"{field}_provider"] = curve["provider"]
        terms[f"{field}_as_of"] = curve["as_of_date"]


def _stale_curve_names(curves):
    return sorted(
        curve["curve_name"]
        for curve in curves.values()
        if curve.get("stale") is True
    )


def _validate_curve_open(session, intent, active, terms):
    asset_class = terms["asset_class"]
    intent["symbol"] = model_contract_symbol(asset_class, intent.get("trade_id"))
    if not is_valid_symbol(intent["symbol"]):
        return None, f"could not assign a valid {asset_class} contract reference"
    if asset_class == "IRS":
        if intent.get("side") != "BUY":
            return None, "an IRS position is directed by its direction term — submit as BUY"
    elif intent.get("side") not in ("BUY", "SELL"):
        return None, "side must be BUY or SELL"
    seen_price = intent.get("client_seen_price")
    if not market_state.is_parseable_price(seen_price):
        return None, "client_seen_price must be a finite number"
    if asset_class != "IRS" and not market_state.is_positive_price(seen_price):
        return None, "client_seen_price must be greater than zero"
    curves, curve_error = _load_terms_curves(terms)
    if curve_error is not None:
        return None, curve_error
    stale_curves = _stale_curve_names(curves)
    if stale_curves and intent.get("stale_curve_acknowledged") is not True:
        return None, (
            "stale curve acknowledgement is required for "
            f"{', '.join(stale_curves)}"
        )

    underlying_quote = None
    provider = None
    if asset_class == "EUROPEAN_OPTION":
        underlying = terms["underlying_symbol"]
        entry = active.get(underlying)
        underlying_intent = {
            "asset_class": entry.asset_class if entry else "EQUITY",
            "market_data_provider": intent.get("market_data_provider"),
            "symbol": underlying,
        }
        provider, provider_error = _resolve_provider(underlying_intent, active)
        if provider_error is not None:
            return None, provider_error
        underlying_quote, state = market_state.current_quote(session, provider, underlying)
        if state is FreshnessState.MISSING:
            return None, f"{provider} has no current quote for {underlying}"
        if state is FreshnessState.STALE:
            return None, f"the {provider} quote for {underlying} is stale"

    price = _model_price(
        terms,
        curves,
        underlying_mid=underlying_quote.mid if underlying_quote else None,
    )
    deviation_error = _model_deviation_error(
        terms, price, intent.get("client_seen_price")
    )
    if deviation_error is not None:
        return None, deviation_error
    _freeze_curve_provenance(terms, curves)
    if stale_curves:
        terms["stale_curve_acknowledged"] = stale_curves

    if underlying_quote is not None:
        quote = market_state.ModelQuote(
            terms["currency"],
            underlying_quote.state,
            provider_timestamp=underlying_quote.provider_timestamp,
            snapshot_id=underlying_quote.snapshot_id,
        )
    else:
        quote = market_state.ModelQuote(
            terms["currency"],
            FreshnessState.LIVE,
            provider_timestamp=_as_of_timestamp(
                curves["discount_curve"]["as_of_date"]
            ),
        )
    return {"terms": terms, "provider": provider, "quote": quote, "price": price}, None


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
    active = load_active_set(session)
    curves = (
        latest_curve_sets(session)
        if asset_class in CURVE_PRICED_ASSET_CLASSES
        else ()
    )
    terms, term_error = _resolve_terms(session, intent, active, curves)
    if terms is None:
        return None, term_error
    quantity = intent.get("quantity")
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, (int, float))
        or not math.isfinite(quantity)
        or quantity < TRADE_QUANTITY_MIN
        or quantity > TRADE_QUANTITY_MAX
    ):
        return None, (
            f"quantity must be between {TRADE_QUANTITY_MIN} and "
            f"{TRADE_QUANTITY_MAX}"
        )
    if asset_class in WHOLE_QUANTITY_ASSET_CLASSES and not float(quantity).is_integer():
        return None, f"{asset_class} quantity must be a whole number"
    if asset_class in ("BOND", "IRS") and quantity != 1:
        size_term = "face amount" if asset_class == "BOND" else "notional"
        return None, f"{asset_class} quantity must be 1; {size_term} defines position size"
    if asset_class in CURVE_PRICED_ASSET_CLASSES:
        return _validate_curve_open(session, intent, active, terms)
    provider, provider_error = _resolve_provider(intent, active)
    if provider_error is not None:
        return None, provider_error
    if intent.get("side") not in ("BUY", "SELL"):
        return None, "side must be BUY or SELL"
    if not market_state.is_positive_price(intent.get("client_seen_price")):
        return None, "client_seen_price must be a finite number greater than zero"
    quote, price, execution_error = _resolve_execution(
        session, intent, provider, intent.get("side")
    )
    if execution_error is not None:
        return None, execution_error
    return {"terms": terms, "provider": provider, "quote": quote, "price": price}, None


def _validate_curve_close(session, intent, trade):
    terms = dict(trade.trade_metadata or {})
    terms.setdefault("asset_class", trade.asset_class)
    curves, curve_error = _load_terms_curves(terms)
    if curve_error is not None:
        return None, curve_error
    provider = None
    underlying_quote = None
    if trade.asset_class == "EUROPEAN_OPTION":
        provider = trade.market_data_provider or DEFAULT_QUOTE_PROVIDER
        underlying = terms.get("underlying_symbol")
        underlying_quote, state = market_state.current_quote(session, provider, underlying)
        if state is FreshnessState.MISSING:
            return None, f"{provider} has no current quote for {underlying}"
    price = _model_price(
        terms,
        curves,
        underlying_mid=underlying_quote.mid if underlying_quote else None,
    )
    deviation_error = _model_deviation_error(
        terms, price, intent.get("client_seen_price")
    )
    if deviation_error is not None:
        return None, deviation_error
    close_provenance = {}
    for field, curve in curves.items():
        close_provenance[f"close_{field}_provider"] = curve["provider"]
        close_provenance[f"close_{field}_as_of"] = curve["as_of_date"]
    if underlying_quote is not None:
        quote = market_state.ModelQuote(
            trade.trade_currency,
            underlying_quote.state,
            provider_timestamp=underlying_quote.provider_timestamp,
            snapshot_id=underlying_quote.snapshot_id,
        )
    else:
        quote = market_state.ModelQuote(
            trade.trade_currency,
            FreshnessState.LIVE,
            provider_timestamp=_as_of_timestamp(
                curves["discount_curve"]["as_of_date"]
            ),
        )
    return {
        "trade": trade,
        "provider": provider,
        "quote": quote,
        "price": price,
        "close_provenance": close_provenance,
    }, None


def validate_close(session, intent, require_seen=True):
    trade_id = parse_uuid(intent.get("trade_id"))
    trade = repository.active_trade(session, trade_id) if trade_id else None
    if trade is None:
        return None, "trade is not open"
    seen_price = intent.get("client_seen_price")
    if require_seen and not market_state.is_parseable_price(seen_price):
        return None, "client_seen_price must be a finite number"
    if (
        require_seen
        and trade.asset_class != "IRS"
        and not market_state.is_positive_price(seen_price)
    ):
        return None, "client_seen_price must be greater than zero"
    if trade.asset_class in CURVE_PRICED_ASSET_CLASSES:
        return _validate_curve_close(session, intent, trade)
    provider = trade.market_data_provider or DEFAULT_QUOTE_PROVIDER
    quote, price, error = _resolve_execution(
        session,
        {**intent, "symbol": trade.symbol},
        provider,
        CLOSING_SIDE.get(trade.side, "SELL"),
        allow_stale=True,
    )
    if error is not None:
        return None, error
    return {"trade": trade, "provider": provider, "quote": quote, "price": price}, None
