"""Instrument catalogue. One class per asset class owns everything the desk needs to
know about it: the pricing model and the market inputs it consumes, the terms that
define a contract, the trade rules and how the contract is identified in storage."""

from abc import ABC, abstractmethod
from decimal import Decimal

from desk_pricing.bond import bond_pv
from desk_pricing.european_option import european_option_pv
from desk_pricing.irs import irs_valuation

MAX_CONTRACT_AMOUNT = 1_000_000_000_000
MAX_OPTION_STRIKE = 1_000_000_000
MAX_MATURITY_YEARS = 50
DEFAULT_VOLATILITY = 0.22
IRS_PAYMENTS_PER_YEAR = {"3M": 4, "6M": 2}

CURVE_FIELDS = ("discount_curve", "projection_curve")


def _field(name, label, kind, **rules):
    return {"name": name, "label": label, "type": kind, **rules}


def _usable_curve(curve):
    if not isinstance(curve, dict):
        return False
    tenors, rates = curve.get("tenors"), curve.get("rates")
    return bool(tenors) and bool(rates) and len(tenors) == len(rates)


MATURITY_FIELD = _field("maturity_years", "MATURITY (YEARS)", "number", gt=0, max=MAX_MATURITY_YEARS)
SETTLEMENT_CURRENCY_FIELD = _field(
    "settlement_currency", "CURRENCY", "choice", choices_source="CURVE_CURRENCIES",
)


class FinancialInstrument(ABC):
    @property
    @abstractmethod
    def asset_class(self):
        pass

    @property
    @abstractmethod
    def model(self):
        pass

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
    deviation_notional = None
    size_term = None
    label = None
    ticket_kind = "spot"

    term_fields = ()
    term_settings = ()
    term_defaults = {}
    contract_fields = ()
    pricing_terms = ()
    derived_terms = ()

    def __init__(self, symbol="", terms=None):
        self.symbol = symbol
        self.terms = terms or {}

    @classmethod
    def has_term(cls, name):
        return any(field["name"] == name for field in cls.term_fields)

    @classmethod
    def complete_terms(cls, terms, raw):
        """Add derived terms and reject inconsistent input; `raw` is the ticket payload."""
        return terms

    @property
    def quote_symbol(self):
        if not self.needs_quote:
            return None
        if self.underlying_field:
            return self.terms.get(self.underlying_field)
        return self.symbol

    def price(self, inputs):
        if self.terms.get("model", self.model) != self.model:
            raise ValueError(f"unsupported pricing model for {self.asset_class}")
        quote = inputs.get("spot") or {}
        spot = quote.get("mid") if quote.get("mid") is not None else quote.get("last")
        curve = inputs.get("curve")
        if (self.needs_quote and spot is None) or (self.needs_curve and not _usable_curve(curve)):
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
    term_fields = (
        SETTLEMENT_CURRENCY_FIELD,
        _field("face_value", "FACE AMOUNT", "number", gt=0, max=MAX_CONTRACT_AMOUNT),
        _field("coupon_rate", "COUPON (%)", "number", ge=0, max=100, unit="percent"),
        MATURITY_FIELD,
        _field("payments_per_year", "PAYMENTS / YEAR", "integer", ge=1, max=12),
        _field("discount_curve", "DISCOUNT CURVE", "choice", choices_source="CURVES",
               role_text="Discounts coupons and principal"),
    )
    contract_fields = ("face_value", "coupon_rate", "maturity_years", "payments_per_year")
    pricing_terms = ("discount_curve",)

    def _value(self, spot, curve):
        return {"price": bond_pv(self.terms, curve)}


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
    term_fields = (
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
    contract_fields = (
        "direction", "notional", "fixed_rate", "maturity_years", "floating_rate_index_tenor",
    )
    pricing_terms = ("discount_curve",)
    derived_terms = ("payments_per_year", "projection_curve", "pricing_approach")

    @classmethod
    def complete_terms(cls, terms, raw):
        if raw.get("projection_curve") not in (None, "", terms["discount_curve"]):
            raise ValueError(
                "IRS uses one selected risk-free curve for discounting and projection"
            )
        return {
            **terms,
            "payments_per_year": IRS_PAYMENTS_PER_YEAR[terms["floating_rate_index_tenor"]],
            "projection_curve": terms["discount_curve"],
            "pricing_approach": "SINGLE_CURVE_APPROXIMATION",
        }

    @property
    def deviation_notional(self):
        return Decimal(str(self.terms["notional"]))

    def _value(self, spot, curve):
        price, details = irs_valuation(self.terms, curve)
        return {"price": price, **details}


class EuropeanOption(FinancialInstrument):
    asset_class = "EUROPEAN_OPTION"
    label = "European option"
    ticket_kind = "premium"
    model = "BLACK_SCHOLES"
    symbol_prefix = "OPT"
    needs_quote = True
    needs_curve = True
    whole_quantity = True
    underlying_field = "underlying_symbol"
    underlying_asset_classes = ("EQUITY",)
    term_fields = (
        _field("underlying_symbol", "UNDERLYING", "choice", choices_source="WATCHLIST_SPOT"),
        _field("option_type", "TYPE", "choice", choices=["CALL", "PUT"],
               labels={"CALL": "Call", "PUT": "Put"}),
        _field("strike", "STRIKE", "number", gt=0, max=MAX_OPTION_STRIKE),
        MATURITY_FIELD,
        _field("discount_curve", "DISCOUNT CURVE", "choice", choices_source="CURVES",
               role_text="Discounts the strike payment"),
    )
    term_settings = (
        _field("multiplier", "CONTRACT MULTIPLIER", "integer", ge=1, max=1_000_000),
        _field("volatility", "VOLATILITY", "number", ge=0, max=10),
    )
    term_defaults = {"multiplier": 1, "volatility": DEFAULT_VOLATILITY}
    contract_fields = ("option_type", "strike", "maturity_years", "multiplier")
    pricing_terms = ("discount_curve", "volatility")

    @property
    def multiplier(self):
        return int(self.terms.get("multiplier", 1))

    def _value(self, spot, curve):
        return {"price": european_option_pv(
            self.terms, spot, curve, self.terms.get("volatility", DEFAULT_VOLATILITY),
        )}


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


def instrument_for(asset_class, symbol="", terms=None) -> FinancialInstrument:
    return instrument_type_for(asset_class)(symbol, terms)
