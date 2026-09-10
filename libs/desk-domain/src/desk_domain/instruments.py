"""Instrument catalogue: one class per asset class.

Class attributes are product rules (ticket fields, trading limits). Instance
attributes are this contract. JSON dicts exist only at the HTTP/DB edge
(`from_dict`, `as_terms`, `contract`, `pricing`).
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from desk_domain.pricing import OPTION_MODELS, OPTION_PRICERS, option_model
from desk_pricing.bond import bond_pv
from desk_pricing.irs import irs_valuation

MAX_CONTRACT_AMOUNT = 1_000_000_000_000
MAX_OPTION_STRIKE = 1_000_000_000
MAX_MATURITY_YEARS = 50
DEFAULT_VOLATILITY = 0.22
IRS_PAYMENTS_PER_YEAR = {"3M": 4, "6M": 2}

CURVE_FIELDS = ("discount_curve", "projection_curve")
_EDGE_KEYS = frozenset({"asset_class", "currency", "settlement_currency", "model"})


def _field(name, label, kind, **rules):
    return {"name": name, "label": label, "type": kind, **rules}


def _remainder(data, *names):
    skip = _EDGE_KEYS | set(names)
    return {key: value for key, value in (data or {}).items() if key not in skip}


def _usable_curve(curve):
    if not isinstance(curve, dict):
        return False
    tenors, rates = curve.get("tenors"), curve.get("rates")
    return bool(tenors) and bool(rates) and len(tenors) == len(rates)


MATURITY_FIELD = _field("maturity_years", "MATURITY (YEARS)", "number", gt=0, max=MAX_MATURITY_YEARS)
SETTLEMENT_CURRENCY_FIELD = _field(
    "settlement_currency", "CURRENCY", "choice", choices_source="CURVE_CURRENCIES",
)
DISCOUNT_CURVE_FIELD = _field(
    "discount_curve", "DISCOUNT CURVE", "choice", choices_source="CURVES",
    role_text="Discounts the strike payment",
)


class FinancialInstrument(ABC):
    asset_class = None
    label = None
    ticket_kind = "spot"
    model = None
    models = ()
    symbol_prefix = None

    needs_quote = False
    needs_curve = False
    underlying_field = None
    underlying_asset_classes = ()
    curve_roles = {"discount_curve": ("DISCOUNT",)}

    whole_quantity = False
    fixed_quantity = None
    allowed_sides = ("BUY", "SELL")
    allows_negative_price = False
    multiplier = 1
    size_term = None

    fields = ()
    defaults = {}

    def __init__(self, symbol="", currency="USD"):
        self.symbol = symbol
        self.currency = currency
        self.extras = {}

    @classmethod
    def from_dict(cls, symbol, data):
        inst = cls(symbol, (data or {}).get("currency", "USD"))
        inst.extras = _remainder(data)
        return inst

    @classmethod
    def has_field(cls, name):
        return any(field["name"] == name for field in cls.fields)

    def uses_curve(self):
        return self.needs_curve

    @property
    def quote_symbol(self):
        if not self.needs_quote:
            return None
        if self.underlying_field:
            return getattr(self, self.underlying_field, None)
        return self.symbol

    @property
    def discount_curve(self):
        return None

    @property
    def projection_curve(self):
        return None

    @property
    def deviation_notional(self):
        return None

    def contract(self):
        return {}

    def pricing(self):
        return {"model": self.model}

    def derived(self):
        return {}

    def as_terms(self):
        terms = {
            **self.contract(),
            **self.pricing(),
            **self.derived(),
            "asset_class": self.asset_class,
            "currency": self.currency,
        }
        if self.underlying_field:
            terms[self.underlying_field] = getattr(self, self.underlying_field, None)
        if self.has_field("settlement_currency"):
            terms["settlement_currency"] = self.currency
        terms.update(self.extras)
        return terms

    def price(self, inputs):
        quote = inputs.get("spot") or {}
        spot = quote.get("mid") if quote.get("mid") is not None else quote.get("last")
        curve = inputs.get("curve")
        if (self.needs_quote and spot is None) or (self.uses_curve() and not _usable_curve(curve)):
            return None
        result = self._value(spot, curve)
        result = {key: Decimal(str(value)) if value is not None else None
                  for key, value in result.items()}
        if result["price"] is None or not result["price"].is_finite():
            return None
        return {**result, "multiplier": self.multiplier}

    @abstractmethod
    def _value(self, spot, curve):
        pass


class SpotInstrument(FinancialInstrument):
    model = "SPOT"
    needs_quote = True
    needs_curve = False
    curve_roles = {}

    def _value(self, spot, curve):
        return {"price": spot}


class Equity(SpotInstrument):
    asset_class = "EQUITY"
    label = "Equity"
    whole_quantity = True


class FX(SpotInstrument):
    asset_class = "FX"
    label = "Foreign exchange"


class Commodity(SpotInstrument):
    asset_class = "COMMODITY"
    label = "Commodity"


class Bond(FinancialInstrument):
    asset_class = "BOND"
    label = "Bond"
    ticket_kind = "bond"
    model = "BOND_DCF"
    needs_curve = True
    symbol_prefix = "BOND"
    fixed_quantity = 1
    size_term = "face_value"
    fields = (
        SETTLEMENT_CURRENCY_FIELD,
        _field("face_value", "FACE AMOUNT", "number", gt=0, max=MAX_CONTRACT_AMOUNT),
        _field("coupon_rate", "COUPON (%)", "number", ge=0, max=100, unit="percent"),
        MATURITY_FIELD,
        _field("payments_per_year", "PAYMENTS / YEAR", "integer", ge=1, max=12),
        _field("discount_curve", "DISCOUNT CURVE", "choice", choices_source="CURVES",
               role_text="Discounts coupons and principal"),
    )

    def __init__(self, symbol, face_value, coupon_rate, maturity_years, payments_per_year,
                 discount_curve, currency="USD"):
        super().__init__(symbol, currency)
        self.face_value = face_value
        self.coupon_rate = coupon_rate
        self.maturity_years = maturity_years
        self.payments_per_year = payments_per_year
        self._discount_curve = discount_curve

    @classmethod
    def from_dict(cls, symbol, data):
        data = dict(data or {})
        inst = cls(
            symbol,
            face_value=data["face_value"],
            coupon_rate=data["coupon_rate"],
            maturity_years=data["maturity_years"],
            payments_per_year=data["payments_per_year"],
            discount_curve=data["discount_curve"],
            currency=data.get("settlement_currency") or data.get("currency", "USD"),
        )
        inst.extras = _remainder(
            data, "face_value", "coupon_rate", "maturity_years",
            "payments_per_year", "discount_curve",
        )
        return inst

    @property
    def discount_curve(self):
        return self._discount_curve

    def contract(self):
        return {
            "face_value": self.face_value,
            "coupon_rate": self.coupon_rate,
            "maturity_years": self.maturity_years,
            "payments_per_year": self.payments_per_year,
        }

    def pricing(self):
        return {"model": self.model, "discount_curve": self.discount_curve}

    def _value(self, spot, curve):
        return {"price": bond_pv(self.contract(), curve)}


class InterestRateSwap(FinancialInstrument):
    asset_class = "IRS"
    label = "Interest rate swap"
    ticket_kind = "swap"
    model = "IRS_SINGLE_CURVE"
    needs_curve = True
    symbol_prefix = "IRS"
    fixed_quantity = 1
    allowed_sides = ("BUY",)
    allows_negative_price = True
    size_term = "notional"
    curve_roles = {"discount_curve": ("DISCOUNT", "PROJECTION")}
    fields = (
        _field("direction", "DIRECTION", "choice",
               choices=["PAY_FIXED_RECEIVE_FLOAT", "RECEIVE_FIXED_PAY_FLOAT"],
               labels={"PAY_FIXED_RECEIVE_FLOAT": "Pay fixed",
                       "RECEIVE_FIXED_PAY_FLOAT": "Receive fixed"}),
        SETTLEMENT_CURRENCY_FIELD,
        _field("notional", "NOTIONAL", "number", gt=0, max=MAX_CONTRACT_AMOUNT),
        _field("fixed_rate", "FIXED RATE (%)", "number", gt=0, max=100, unit="percent"),
        MATURITY_FIELD,
        _field("floating_rate_index_tenor", "FLOATING INDEX TENOR", "choice",
               choices=["3M", "6M"], labels={"3M": "3-month", "6M": "6-month"}),
        _field("discount_curve", "DISCOUNT / PROJECTION CURVE", "choice",
               choices_source="CURVES",
               role_text="Discounts both legs and implies the floating payments"),
    )

    def __init__(self, symbol, direction, notional, fixed_rate, maturity_years,
                 floating_rate_index_tenor, discount_curve, currency="USD"):
        super().__init__(symbol, currency)
        if floating_rate_index_tenor not in IRS_PAYMENTS_PER_YEAR:
            raise ValueError("invalid floating_rate_index_tenor")
        self.direction = direction
        self.notional = notional
        self.fixed_rate = fixed_rate
        self.maturity_years = maturity_years
        self.floating_rate_index_tenor = floating_rate_index_tenor
        self.payments_per_year = IRS_PAYMENTS_PER_YEAR[floating_rate_index_tenor]
        self._discount_curve = discount_curve
        self.pricing_approach = "SINGLE_CURVE_APPROXIMATION"

    @classmethod
    def from_dict(cls, symbol, data):
        data = dict(data or {})
        if data.get("projection_curve") not in (None, "", data.get("discount_curve")):
            raise ValueError(
                "IRS uses one selected risk-free curve for discounting and projection"
            )
        inst = cls(
            symbol,
            direction=data["direction"],
            notional=data["notional"],
            fixed_rate=data["fixed_rate"],
            maturity_years=data["maturity_years"],
            floating_rate_index_tenor=data["floating_rate_index_tenor"],
            discount_curve=data["discount_curve"],
            currency=data.get("settlement_currency") or data.get("currency", "USD"),
        )
        inst.extras = _remainder(
            data, "direction", "notional", "fixed_rate", "maturity_years",
            "floating_rate_index_tenor", "discount_curve", "payments_per_year",
            "projection_curve", "pricing_approach",
        )
        return inst

    @property
    def discount_curve(self):
        return self._discount_curve

    @property
    def projection_curve(self):
        return self._discount_curve

    @property
    def deviation_notional(self):
        return Decimal(str(self.notional))

    def contract(self):
        return {
            "direction": self.direction,
            "notional": self.notional,
            "fixed_rate": self.fixed_rate,
            "maturity_years": self.maturity_years,
            "floating_rate_index_tenor": self.floating_rate_index_tenor,
        }

    def pricing(self):
        return {"model": self.model, "discount_curve": self.discount_curve}

    def derived(self):
        return {
            "payments_per_year": self.payments_per_year,
            "projection_curve": self.projection_curve,
            "pricing_approach": self.pricing_approach,
        }

    def _value(self, spot, curve):
        price, details = irs_valuation(
            {**self.contract(), "payments_per_year": self.payments_per_year}, curve,
        )
        return {"price": price, **details}


class EuropeanOption(FinancialInstrument):
    asset_class = "EUROPEAN_OPTION"
    label = "European option"
    ticket_kind = "premium"
    model = "BLACK_SCHOLES"
    models = OPTION_MODELS
    symbol_prefix = "OPT"
    needs_quote = True
    needs_curve = any(spec["needs_curve"] for spec in OPTION_MODELS)
    whole_quantity = True
    underlying_field = "underlying_symbol"
    underlying_asset_classes = ("EQUITY",)
    defaults = {"multiplier": 1, "volatility": DEFAULT_VOLATILITY}
    fields = (
        _field("underlying_symbol", "UNDERLYING", "choice", choices_source="WATCHLIST_SPOT"),
        _field("option_type", "TYPE", "choice", choices=["CALL", "PUT"],
               labels={"CALL": "Call", "PUT": "Put"}),
        _field("strike", "STRIKE", "number", gt=0, max=MAX_OPTION_STRIKE),
        MATURITY_FIELD,
        DISCOUNT_CURVE_FIELD,
        _field("multiplier", "CONTRACT MULTIPLIER", "integer", ge=1, max=1_000_000, hidden=True),
        _field("volatility", "VOLATILITY", "number", ge=0, max=10, hidden=True),
    )

    def __init__(self, symbol, option_type, strike, maturity_years, underlying_symbol,
                 multiplier=1, model="BLACK_SCHOLES", discount_curve=None,
                 volatility=DEFAULT_VOLATILITY, currency="USD"):
        super().__init__(symbol, currency)
        self.option_type = option_type
        self.strike = strike
        self.maturity_years = maturity_years
        self.underlying_symbol = underlying_symbol
        self.multiplier = int(multiplier)
        self.model = model
        self._discount_curve = discount_curve
        self.volatility = volatility

    @classmethod
    def from_dict(cls, symbol, data):
        data = dict(data or {})
        model = data.get("model", cls.model)
        if option_model(model) is None:
            raise ValueError(f"unsupported pricing model {model} for {cls.asset_class}")
        inst = cls(
            symbol,
            option_type=data["option_type"],
            strike=data["strike"],
            maturity_years=data["maturity_years"],
            underlying_symbol=data["underlying_symbol"],
            multiplier=data.get("multiplier", 1),
            model=model,
            discount_curve=data.get("discount_curve"),
            volatility=data.get("volatility", DEFAULT_VOLATILITY),
            currency=data.get("currency", "USD"),
        )
        inst.extras = _remainder(
            data, "option_type", "strike", "maturity_years", "underlying_symbol",
            "multiplier", "discount_curve", "volatility",
        )
        return inst

    @property
    def discount_curve(self):
        return self._discount_curve

    def uses_curve(self):
        spec = option_model(self.model)
        return spec["needs_curve"] if spec else True

    def contract(self):
        return {
            "option_type": self.option_type,
            "strike": self.strike,
            "maturity_years": self.maturity_years,
            "multiplier": self.multiplier,
        }

    def pricing(self):
        payload = {"model": self.model}
        if self.uses_curve():
            if self.discount_curve is not None:
                payload["discount_curve"] = self.discount_curve
            payload["volatility"] = self.volatility
        return payload

    def _value(self, spot, curve):
        try:
            pricer = OPTION_PRICERS[self.model]
        except KeyError:
            raise ValueError(f"unsupported pricing model {self.model} for {self.asset_class}") from None
        return pricer(
            {
                "option_type": self.option_type,
                "strike": self.strike,
                "maturity_years": self.maturity_years,
                "volatility": self.volatility,
            },
            spot,
            curve,
        )


INSTRUMENT_TYPES = {
    cls.asset_class: cls
    for cls in (Equity, FX, Commodity, Bond, InterestRateSwap, EuropeanOption)
}


def type_view(instrument_type):
    return {
        "label": instrument_type.label,
        "ticket_kind": instrument_type.ticket_kind,
    }


def type_view_for(asset_class):
    return type_view(instrument_type_for(asset_class))


def instrument_type_for(asset_class):
    try:
        return INSTRUMENT_TYPES[asset_class]
    except (KeyError, TypeError):
        raise ValueError(f"unsupported asset class: {asset_class}") from None


def instrument_for(asset_class, symbol="", data=None):
    cls = instrument_type_for(asset_class)
    if data is not None:
        try:
            return cls.from_dict(symbol, data)
        except KeyError as exc:
            raise ValueError(f"missing term: {exc.args[0]}") from exc
    if cls.fields:
        raise ValueError(f"{asset_class} requires instrument terms")
    return cls(symbol)
