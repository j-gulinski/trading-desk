from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class Instrument:
    asset_class: str
    symbol: str
    meta: dict = field(default_factory=dict)
    current_price: Optional[Decimal] = None


@dataclass
class Position:
    side: str
    quantity: Decimal
    trade_price: Decimal
    instrument: Instrument


@dataclass
class ScenarioRequest:
    position: Position
    shock: float
    market_data_provider: str | None

    @classmethod
    def from_body(cls, body: dict) -> "ScenarioRequest":
        try:
            pos = body["position"]
            inst = pos["instrument"]
            raw_current = inst.get("current_price")
            return cls(
                position=Position(
                    side=pos["side"],
                    quantity=Decimal(str(pos["quantity"])),
                    trade_price=Decimal(str(pos["trade_price"])),
                    instrument=Instrument(
                        asset_class=inst["asset_class"],
                        symbol=inst.get("symbol", ""),
                        meta=inst.get("meta") or {},
                        current_price=Decimal(str(raw_current)) if raw_current is not None else None,
                    ),
                ),
                shock=float(body["shock"]),
                market_data_provider=body.get("market_data_provider"),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"invalid request: {e}")
