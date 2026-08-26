from shared.audit import write_audit
from app.config import SERVICE_NAME


def audit_curve_set(curve_set, created):
    write_audit(
        SERVICE_NAME,
        "CURVE_SET_WRITTEN",
        f"{curve_set.provider} {'published' if created else 'revised'} "
        f"{curve_set.curve_name} as of {curve_set.as_of_date}",
        entity_type="CURVE",
        entity_id=f"{curve_set.provider}:{curve_set.curve_name}",
        payload={
            "provider": curve_set.provider,
            "curve_name": curve_set.curve_name,
            "curve_basis": curve_set.curve_basis,
            "currency": curve_set.currency,
            "as_of_date": str(curve_set.as_of_date),
            "points": len(curve_set.points),
        },
    )


def audit_first_quote(provider, quote):
    write_audit(
        SERVICE_NAME,
        "QUOTE_WRITTEN",
        f"{provider} began quoting {quote.symbol}",
        entity_type="QUOTE",
        entity_id=f"{provider}:{quote.symbol}",
        payload={
            "provider": provider,
            "symbol": quote.symbol,
            "asset_class": quote.asset_class,
            "mid": str(quote.mid),
            "price_basis": quote.price_basis.value,
            "quote_grade": quote.quote_grade.value,
            "provider_timestamp": quote.provider_timestamp.isoformat()
            if quote.provider_timestamp else None,
        },
    )
