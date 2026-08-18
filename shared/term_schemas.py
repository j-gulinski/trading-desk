DEFAULT_CURVE = "USD_GOV"
DEFAULT_VOLATILITY = 0.22

TERM_SCHEMAS = {
    "EUROPEAN_OPTION": {
        "customizable": True,
        "defaults": {"multiplier": 1, "curve": DEFAULT_CURVE, "volatility": DEFAULT_VOLATILITY},
        "fields": [
            {"name": "underlying_symbol", "label": "UNDERLYING", "type": "choice",
             "choices_source": "WATCHLIST_SPOT"},
            {"name": "option_type", "label": "TYPE", "type": "choice",
             "choices": ["CALL", "PUT"], "labels": {"CALL": "Call", "PUT": "Put"}},
            {"name": "strike", "label": "STRIKE", "type": "number", "gt": 0},
            {"name": "maturity_years", "label": "MATURITY (YEARS)", "type": "number",
             "gt": 0, "max": 50},
        ],
    },
    "IRS": {
        "customizable": True,
        "defaults": {"curve": DEFAULT_CURVE},
        "fields": [
            {"name": "direction", "label": "DIRECTION", "type": "choice",
             "choices": ["PAY_FIXED_RECEIVE_FLOAT", "RECEIVE_FIXED_PAY_FLOAT"],
             "labels": {"PAY_FIXED_RECEIVE_FLOAT": "Pay fixed",
                        "RECEIVE_FIXED_PAY_FLOAT": "Receive fixed"}},
            {"name": "notional", "label": "NOTIONAL (USD)", "type": "number", "gt": 0},
            {"name": "fixed_rate", "label": "FIXED RATE (%)", "type": "number",
             "gt": 0, "max": 1, "unit": "percent"},
            {"name": "maturity_years", "label": "MATURITY (YEARS)", "type": "number",
             "gt": 0, "max": 50},
            {"name": "payments_per_year", "label": "PAYMENTS / YEAR", "type": "integer",
             "ge": 1, "max": 12},
        ],
    },
}


def _field_choices(field, underlying_choices):
    if field.get("choices_source") == "WATCHLIST_SPOT":
        return list(underlying_choices)
    return field["choices"]


def public_term_schemas(underlying_choices):
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
            public_field["choices"] = _field_choices(field, underlying_choices)
            fields.append(public_field)
        schemas[asset_class] = {**schema, "fields": fields}
    return schemas


def validate_terms(asset_class, raw, underlying_choices=()):
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
            if value not in _field_choices(field, underlying_choices):
                return None, f"invalid {name}"
            terms[name] = value
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{name} must be a number"
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

    terms["asset_class"] = asset_class
    terms["currency"] = "USD"
    return terms, None
