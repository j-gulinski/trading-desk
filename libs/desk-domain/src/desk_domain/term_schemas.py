"""Validation of ticket terms against the instrument catalogue, and the public schema
the ticket reads. Nothing here knows a specific asset class."""

import math

from desk_domain.instruments import CURVE_FIELDS, INSTRUMENT_TYPES, instrument_type_for, type_view


def curve_currencies(curves):
    return sorted({curve["currency"] for curve in curves})


def _approved_curves(instrument_type, field_name, curves):
    required = {
        f"{instrument_type.asset_class}:{role}"
        for role in instrument_type.curve_roles.get(field_name, ())
    }
    return [curve for curve in curves if required.issubset(set(curve.get("uses", ())))]


def _field_choices(instrument_type, field, spot_catalog, curves, approved_only=False):
    source = field.get("choices_source")
    if source == "WATCHLIST_SPOT":
        return [
            symbol for symbol, entry in spot_catalog.items()
            if entry["asset_class"] in instrument_type.underlying_asset_classes
        ]
    if source == "CURVES":
        eligible = _approved_curves(instrument_type, field["name"], curves) if approved_only else curves
        return [curve["curve_name"] for curve in eligible]
    if source == "CURVE_CURRENCIES":
        return curve_currencies(curves)
    return field["choices"]


def public_term_schemas(spot_catalog, curves=()):
    schemas = {}
    for asset_class, instrument_type in INSTRUMENT_TYPES.items():
        fields = []
        for field in instrument_type.term_fields:
            if field["type"] != "choice":
                fields.append(field)
                continue
            public_field = {
                key: value for key, value in field.items() if key != "choices_source"
            }
            public_field["choices"] = _field_choices(
                instrument_type, field, spot_catalog, curves, approved_only=True,
            )
            if field.get("choices_source") == "CURVES":
                public_field["choices_source"] = "CURVES"
            fields.append(public_field)
        schemas[asset_class] = {
            **type_view(instrument_type),
            "model": instrument_type.model,
            "customizable": bool(instrument_type.term_fields),
            "defaults": dict(instrument_type.term_defaults),
            "fields": fields,
            "needs_quote": instrument_type.needs_quote,
            "needs_curve": instrument_type.needs_curve,
            "underlying_field": instrument_type.underlying_field,
            "fixed_quantity": instrument_type.fixed_quantity,
            "whole_quantity": instrument_type.whole_quantity,
            "allowed_sides": list(instrument_type.allowed_sides),
            "allows_negative_price": instrument_type.allows_negative_price,
            "size_term": instrument_type.size_term,
        }
    return schemas


def _use_label(field_name):
    return "project" if field_name == "projection_curve" else "discount"


def _curve_guards(instrument_type, terms, curves):
    by_name = {curve["curve_name"]: curve for curve in curves}
    asset_class = instrument_type.asset_class
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
        for role in instrument_type.curve_roles.get(field_name, ()):
            if f"{asset_class}:{role}" not in curve.get("uses", ()):
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


def _terms_currency(instrument_type, terms, spot_catalog):
    if "settlement_currency" in terms:
        return terms["settlement_currency"]
    underlying = terms.get(instrument_type.underlying_field) if instrument_type.underlying_field else None
    if underlying is not None:
        return (spot_catalog.get(underlying) or {}).get("currency") or "USD"
    return "USD"


def _number(field, value):
    if isinstance(value, bool):
        raise ValueError(f"{field['name']} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field['name']} must be a number") from None
    if not math.isfinite(number):
        raise ValueError(f"{field['name']} must be a finite number")
    if field["type"] == "integer":
        if not number.is_integer():
            raise ValueError(f"{field['name']} must be a whole number")
        number = int(number)
    if "gt" in field and not number > field["gt"]:
        raise ValueError(f"{field['name']} must be greater than {field['gt']}")
    if "ge" in field and not number >= field["ge"]:
        raise ValueError(f"{field['name']} must be at least {field['ge']}")
    if "max" in field and not number <= field["max"]:
        raise ValueError(f"{field['name']} must be at most {field['max']}")
    return number


def validate_terms(asset_class, raw, spot_catalog=None, curves=()):
    try:
        instrument_type = instrument_type_for(asset_class)
    except ValueError as exc:
        return None, str(exc)
    if not instrument_type.term_fields:
        return None, f"{asset_class} does not accept custom terms"
    if not isinstance(raw, dict):
        return None, "terms must be an object"
    if raw.get("model", instrument_type.model) != instrument_type.model:
        return None, f"unsupported pricing model for {asset_class}"

    spot_catalog = spot_catalog or {}
    terms = dict(instrument_type.term_defaults)
    for field in (*instrument_type.term_fields, *instrument_type.term_settings):
        name = field["name"]
        value = raw.get(name, terms.get(name))
        if value is None or value == "":
            return None, f"missing term: {name}"
        if field["type"] == "choice":
            if value not in _field_choices(instrument_type, field, spot_catalog, curves):
                return None, f"invalid {name}"
            terms[name] = value
            continue
        try:
            terms[name] = _number(field, value)
        except ValueError as exc:
            return None, str(exc)

    try:
        terms = instrument_type.complete_terms(terms, raw)
    except ValueError as exc:
        return None, str(exc)
    terms["asset_class"] = asset_class
    terms["currency"] = _terms_currency(instrument_type, terms, spot_catalog)

    guard_error = _curve_guards(instrument_type, terms, curves)
    if guard_error is not None:
        return None, guard_error
    return terms, None
