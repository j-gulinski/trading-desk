from shared.freshness import QuoteGrade

FINNHUB = "FINNHUB"
TWELVE_DATA = "TWELVE_DATA"
ALPHA_VANTAGE = "ALPHA_VANTAGE"
NBP = "NBP"
ECB = "ECB"
FRED = "FRED"

GROUP_QUOTE = "QUOTE"
GROUP_OFFICIAL = "OFFICIAL"

PROVIDERS = {
    FINNHUB: {
        "group": GROUP_QUOTE,
        "quotes": {"EQUITY": QuoteGrade.REALTIME},
        "serves_curves": False,
    },
    TWELVE_DATA: {
        "group": GROUP_QUOTE,
        "quotes": {
            "EQUITY": QuoteGrade.REALTIME,
            "FX": QuoteGrade.REALTIME,
            "COMMODITY": QuoteGrade.REALTIME,
        },
        "serves_curves": False,
    },
    ALPHA_VANTAGE: {
        "group": GROUP_QUOTE,
        "quotes": {"EQUITY": QuoteGrade.EOD, "FX": QuoteGrade.REALTIME},
        "serves_curves": False,
    },
    NBP: {
        "group": GROUP_OFFICIAL,
        "quotes": {"FX": QuoteGrade.REFERENCE, "COMMODITY": QuoteGrade.REFERENCE},
        "serves_curves": True,
    },
    ECB: {
        "group": GROUP_OFFICIAL,
        "quotes": {"FX": QuoteGrade.REFERENCE},
        "serves_curves": True,
    },
    FRED: {
        "group": GROUP_OFFICIAL,
        "quotes": {},
        "serves_curves": True,
    },
}


QUOTE_PROVIDERS = tuple(
    name for name, spec in PROVIDERS.items() if spec["group"] == GROUP_QUOTE
)


def quote_grade(provider, asset_class):
    return PROVIDERS[provider]["quotes"].get(asset_class)


def supports_quotes(provider, asset_class):
    return quote_grade(provider, asset_class) is not None


def capable_providers(asset_class, providers=QUOTE_PROVIDERS):
    return tuple(p for p in providers if supports_quotes(p, asset_class))
