from shared.audit import write_audit
from app.config import SERVICE_NAME


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
