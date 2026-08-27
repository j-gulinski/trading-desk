import math

DEFAULT_VOLATILITY = 0.22
IRS_PAYMENTS_PER_YEAR = {"3M": 4, "6M": 2}
MAX_CONTRACT_AMOUNT = 1_000_000_000_000
MAX_OPTION_STRIKE = 1_000_000_000

TERM_SCHEMAS = {
    "EUROPEAN_OPTION": {
        "customizable": True,
        "defaults": {"multiplier": 1, "volatility": DEFAULT_VOLATILITY},
        "fields": [
            {"name": "underlying_symbol", "label": "UNDERLYING", "type": "choice",
             "choices_source": "WATCHLIST_SPOT"},
            {"name": "option_type", "label": "TYPE", "type": "choice",
             "choices": ["CALL", "PUT"], "labels": {"CALL": "Call", "PUT": "Put"}},
            {"name": "strike", "label": "STRIKE", "type": "number", "gt": 0,
             "max": MAX_OPTION_STRIKE},
            {"name": "maturity_years", "label": "MATURITY (YEARS)", "type": "number",
             "gt": 0, "max": 50},
            {"name": "discount_curve", "label": "DISCOUNT CURVE", "type": "choice",
             "choices_source": "CURVES"},
        ],
    },
    "IRS": {
        "customizable": True,
        "defaults": {},
        "fields": [
            {"name": "direction", "label": "DIRECTION", "type": "choice",
             "choices": ["PAY_FIXED_RECEIVE_FLOAT", "RECEIVE_FIXED_PAY_FLOAT"],
             "labels": {"PAY_FIXED_RECEIVE_FLOAT": "Pay fixed",
                        "RECEIVE_FIXED_PAY_FLOAT": "Receive fixed"}},
            {"name": "settlement_currency", "label": "CURRENCY", "type": "choice",
             "choices_source": "CURVE_CURRENCIES"},
            {"name": "notional", "label": "NOTIONAL", "type": "number", "gt": 0,
             "max": MAX_CONTRACT_AMOUNT},
            {"name": "fixed_rate", "label": "FIXED RATE (%)", "type": "number",
             "gt": 0, "max": 100, "unit": "percent"},
            {"name": "maturity_years", "label": "MATURITY (YEARS)", "type": "number",
             "gt": 0, "max": 50},
            {"name": "floating_rate_index_tenor", "label": "FLOATING INDEX TENOR",
             "type": "choice", "choices": ["3M", "6M"],
             "labels": {"3M": "3-month", "6M": "6-month"}},
            {"name": "discount_curve", "label": "DISCOUNT / PROJECTION CURVE",
             "type": "choice",
             "choices_source": "CURVES"},
        ],
    },
    "BOND": {
        "customizable": True,
        "defaults": {},
        "fields": [
            {"name": "settlement_currency", "label": "CURRENCY", "type": "choice",
             "choices_source": "CURVE_CURRENCIES"},
            {"name": "face_value", "label": "FACE AMOUNT", "type": "number", "gt": 0,
             "max": MAX_CONTRACT_AMOUNT},
            {"name": "coupon_rate", "label": "COUPON (%)", "type": "number",
             "ge": 0, "max": 100, "unit": "percent"},
            {"name": "maturity_years", "label": "MATURITY (YEARS)", "type": "number",
             "gt": 0, "max": 50},
            {"name": "payments_per_year", "label": "PAYMENTS / YEAR", "type": "integer",
             "ge": 1, "max": 12},
            {"name": "discount_curve", "label": "DISCOUNT CURVE", "type": "choice",
             "choices_source": "CURVES"},
        ],
    },
}

CURVE_FIELDS = ("discount_curve", "projection_curve")


def curve_currencies(curves):
    return sorted({curve["currency"] for curve in curves})


def _field_choices(field, underlying_choices, curves):
    source = field.get("choices_source")
    if source == "WATCHLIST_SPOT":
        return list(underlying_choices)
    if source == "CURVES":
        return [curve["curve_name"] for curve in curves]
    if source == "CURVE_CURRENCIES":
        return curve_currencies(curves)
    return field["choices"]


def _public_curve_choices(asset_class, field_name, curves):
    required_uses = {_trade_use(asset_class, field_name)}
    if asset_class == "IRS":
        required_uses = {"IRS:DISCOUNT", "IRS:PROJECTION"}
    return [
        curve["curve_name"]
        for curve in curves
        if required_uses.issubset(set(curve.get("uses", ())))
    ]


def public_term_schemas(underlying_choices, curves=()):
    schemas = {}
    for asset_class, schema in TERM_SCHEMAS.items():
        fields = []
        for field in schema["fields"]:
            if field["type"] != "choice":
                fields.append(field)
                continue
            public_field = {
                key: value for key, value in field.items() if key != "choices_source"
            }
            public_field["choices"] = (
                _public_curve_choices(asset_class, field["name"], curves)
                if field.get("choices_source") == "CURVES"
                else _field_choices(field, underlying_choices, curves)
            )
            if field.get("choices_source") == "CURVES":
                public_field["choices_source"] = "CURVES"
            fields.append(public_field)
        schemas[asset_class] = {**schema, "fields": fields}
    return schemas


def _use_label(field_name):
    return "project" if field_name == "projection_curve" else "discount"


def _trade_use(asset_class, field_name):
    role = "PROJECTION" if field_name == "projection_curve" else "DISCOUNT"
    return f"{asset_class}:{role}"


def _curve_guards(asset_class, terms, curves):
    by_name = {curve["curve_name"]: curve for curve in curves}
    currency = terms.get("settlement_currency") or terms.get("currency")
    for field_name in CURVE_FIELDS:
        curve_name = terms.get(field_name)
        if curve_name is None:
            continue
        curve = by_name[curve_name]
        if currency is not None and curve["currency"] != currency:
            return (
                f"a {currency} {asset_class} cannot {_use_label(field_name)} on "
                f"{curve_name} — it is a {curve['currency']} curve"
            )
        if _trade_use(asset_class, field_name) not in curve.get("uses", ()):
            return (
                f"{curve_name} is not approved as the {_use_label(field_name)} curve "
                f"for {asset_class}"
            )
    projection = by_name.get(terms.get("projection_curve"))
    leg_tenor = terms.get("floating_rate_index_tenor")
    if projection is not None and leg_tenor is not None \
            and projection.get("index_tenor") not in (None, leg_tenor):
        return (
            f"the floating leg pays a {leg_tenor} index but "
            f"{projection['curve_name']} is a {projection['index_tenor']} index curve"
        )
    return None


def validate_terms(asset_class, raw, underlying_choices=(), curves=(),
                   underlying_currency_of=None):
    schema = TERM_SCHEMAS.get(asset_class)
    if schema is None or not schema.get("customizable"):
        return None, f"{asset_class} does not accept custom terms"
    if not isinstance(raw, dict):
        return None, "terms must be an object"

    terms = dict(schema.get("defaults") or {})
    for field in schema["fields"]:
        name = field["name"]
        value = raw.get(name)
        if value is None or value == "":
            return None, f"missing term: {name}"
        if field["type"] == "choice":
            if value not in _field_choices(field, underlying_choices, curves):
                return None, f"invalid {name}"
            terms[name] = value
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{name} must be a number"
        if not math.isfinite(number):
            return None, f"{name} must be a finite number"
        if field["type"] == "integer":
            if not number.is_integer():
                return None, f"{name} must be a whole number"
            number = int(number)
        if "gt" in field and not number > field["gt"]:
            return None, f"{name} must be greater than {field['gt']}"
        if "ge" in field and not number >= field["ge"]:
            return None, f"{name} must be at least {field['ge']}"
        if "max" in field and not number <= field["max"]:
            return None, f"{name} must be at most {field['max']}"
        terms[name] = number

    if asset_class == "IRS":
        terms["payments_per_year"] = IRS_PAYMENTS_PER_YEAR[
            terms["floating_rate_index_tenor"]
        ]
        supplied_projection = raw.get("projection_curve")
        if supplied_projection not in (None, "", terms["discount_curve"]):
            return None, (
                "IRS uses one selected risk-free curve for discounting and projection"
            )
        terms["projection_curve"] = terms["discount_curve"]
        terms["pricing_approach"] = "SINGLE_CURVE_APPROXIMATION"

    terms["asset_class"] = asset_class
    if "settlement_currency" in terms:
        terms["currency"] = terms["settlement_currency"]
    elif "underlying_symbol" in terms:
        underlying_currency = (
            underlying_currency_of.get(terms["underlying_symbol"])
            if underlying_currency_of else None
        )
        terms["currency"] = underlying_currency or "USD"
    else:
        terms["currency"] = "USD"

    guard_error = _curve_guards(asset_class, terms, curves)
    if guard_error is not None:
        return None, guard_error
    return terms, None
