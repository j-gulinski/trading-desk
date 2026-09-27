"""Option engines the ticket can name. Not a second instrument hierarchy."""

from desk_pricing.european_option import black_scholes, intrinsic

OPTION_MODELS = {
    "BLACK_SCHOLES": {"label": "Black–Scholes", "needs_curve": True, "pricer": black_scholes},
    "INTRINSIC": {"label": "Intrinsic value", "needs_curve": False, "pricer": intrinsic},
}


def public_models(models):
    return [
        {"name": name, "label": spec["label"], "needs_curve": spec["needs_curve"]}
        for name, spec in models.items()
    ]
