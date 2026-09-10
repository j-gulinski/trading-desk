"""Split validated terms into what the instrument row stores and what trade metadata
keeps, and rebuild the full terms the pricing and trade code consume."""

from dataclasses import dataclass

from desk_domain.instruments import instrument_type_for


@dataclass(frozen=True)
class ContractData:
    terms: dict
    pricing: dict
    opening: dict
    closing: dict

    def metadata(self):
        return {"pricing": self.pricing, "open": self.opening, "close": self.closing}


def split_terms(instrument):
    terms = instrument.terms
    contract = {key: terms[key] for key in instrument.contract_fields if key in terms}
    pricing = {"model": instrument.model,
               **{key: terms[key] for key in instrument.pricing_terms if key in terms}}
    ignored = set(contract) | set(pricing) | set(instrument.derived_terms) | {
        "asset_class", "currency", "settlement_currency", instrument.underlying_field,
    }
    opening, closing = {}, {}
    for key, value in terms.items():
        if key.startswith("close_"):
            closing[key.removeprefix("close_")] = value
        elif key not in ignored:
            opening[key] = value
    return ContractData(contract, pricing, opening, closing)


def effective_terms(instrument_type, currency, contract, metadata, underlying_symbol=None):
    pricing = metadata.get("pricing") or {}
    if pricing.get("model") != instrument_type.model:
        raise ValueError(f"unsupported pricing model for {instrument_type.asset_class}")
    terms = {**(metadata.get("open") or {}), **pricing, **contract,
             "asset_class": instrument_type.asset_class, "currency": currency}
    terms.update({f"close_{key}": value for key, value in (metadata.get("close") or {}).items()})
    if instrument_type.has_term("settlement_currency"):
        terms["settlement_currency"] = currency
    if underlying_symbol is not None and instrument_type.underlying_field:
        terms[instrument_type.underlying_field] = underlying_symbol
    return instrument_type.complete_terms(terms, {})


def trade_terms(trade):
    instrument = trade.instrument
    return effective_terms(
        instrument_type_for(instrument.asset_class), instrument.currency, instrument.terms,
        trade.trade_metadata or {},
        instrument.underlying.symbol if instrument.underlying else None,
    )


def with_close_metadata(metadata, provenance):
    return {**(metadata or {}), "close": {
        key.removeprefix("close_"): value for key, value in provenance.items()
    }}
