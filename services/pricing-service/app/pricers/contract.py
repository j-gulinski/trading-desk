"""One explicit contract implemented by every asset-class pricer."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PricerRegistration:
    asset_classes: tuple[str, ...]
    load_inputs: Callable[[str | None, dict, str | None], dict]
    calculate: Callable[[dict, dict], tuple | None]
    shock_inputs: Callable[[dict, float], dict | None]
    details: Callable[[dict, dict], dict] = lambda _terms, _inputs: {}

    def __post_init__(self):
        if not self.asset_classes:
            raise ValueError("a pricer must declare at least one asset class")
