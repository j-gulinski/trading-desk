"""Option engines the ticket can name. Not a second instrument hierarchy."""

from desk_pricing.european_option import black_scholes, intrinsic

OPTION_MODELS = (
    {"name": "BLACK_SCHOLES", "label": "Black–Scholes", "needs_curve": True},
    {"name": "INTRINSIC", "label": "Intrinsic value", "needs_curve": False},
)

OPTION_PRICERS = {
    "BLACK_SCHOLES": black_scholes,
    "INTRINSIC": intrinsic,
}


def option_model(name):
    for spec in OPTION_MODELS:
        if spec["name"] == name:
            return spec
    return None
