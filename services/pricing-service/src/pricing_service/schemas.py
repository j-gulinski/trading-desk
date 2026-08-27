from dataclasses import dataclass, field
from decimal import Decimal
import math
from typing import Optional

from desk_domain.symbols import (
    CURVE_PRICED_ASSET_CLASSES,
    SPOT_ASSET_CLASSES,
    TRADE_QUANTITY_MAX,
    TRADE_QUANTITY_MIN,
    WHOLE_QUANTITY_ASSET_CLASSES,
    is_valid_symbol,
)


SUPPORTED_ASSET_CLASSES = (*SPOT_ASSET_CLASSES, *CURVE_PRICED_ASSET_CLASSES)
MAX_SPOT_SHOCK = 10.0
MAX_CURVE_SHOCK_BPS = 10_000.0


def _decimal(value, label):
    try:
        number = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not number.is_finite():
        raise ValueError(f"{label} must be finite")
    return number


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
            if not isinstance(body, dict):
                raise ValueError("request body must be an object")
            pos = body["position"]
            if not isinstance(pos, dict):
                raise ValueError("position must be an object")
            inst = pos["instrument"]
            if not isinstance(inst, dict):
                raise ValueError("instrument must be an object")
            meta = inst.get("meta") or {}
            if not isinstance(meta, dict):
                raise ValueError("instrument.meta must be an object")
            asset_class = inst["asset_class"]
            if asset_class not in SUPPORTED_ASSET_CLASSES:
                raise ValueError(f"unsupported asset_class {asset_class}")
            symbol = inst.get("symbol", "")
            if not is_valid_symbol(symbol):
                raise ValueError("instrument.symbol must be a valid symbol")
            side = pos["side"]
            if side not in ("BUY", "SELL"):
                raise ValueError("side must be BUY or SELL")
            quantity = _decimal(pos["quantity"], "quantity")
            if not TRADE_QUANTITY_MIN <= quantity <= TRADE_QUANTITY_MAX:
                raise ValueError(
                    f"quantity must be between {TRADE_QUANTITY_MIN} and "
                    f"{TRADE_QUANTITY_MAX}"
                )
            if asset_class in WHOLE_QUANTITY_ASSET_CLASSES \
                    and quantity != quantity.to_integral_value():
                raise ValueError(f"{asset_class} quantity must be a whole number")
            if asset_class in ("BOND", "IRS") and quantity != 1:
                raise ValueError(f"{asset_class} quantity must be 1")
            trade_price = _decimal(pos["trade_price"], "trade_price")
            if asset_class != "IRS" and trade_price <= 0:
                raise ValueError("trade_price must be greater than zero")
            raw_current = inst.get("current_price")
            current_price = (
                _decimal(raw_current, "current_price")
                if raw_current is not None else None
            )
            if asset_class != "IRS" and current_price is not None \
                    and current_price <= 0:
                raise ValueError("current_price must be greater than zero")
            shock = float(body["shock"])
            if not math.isfinite(shock):
                raise ValueError("shock must be finite")
            if asset_class in (*SPOT_ASSET_CLASSES, "EUROPEAN_OPTION"):
                if not -1.0 < shock <= MAX_SPOT_SHOCK:
                    raise ValueError(
                        f"spot shock must be greater than -1 and at most {MAX_SPOT_SHOCK}"
                    )
            elif abs(shock) > MAX_CURVE_SHOCK_BPS:
                raise ValueError(
                    f"curve shock must be between {-MAX_CURVE_SHOCK_BPS:g} and "
                    f"{MAX_CURVE_SHOCK_BPS:g} basis points"
                )
            provider = body.get("market_data_provider")
            if provider is not None and (
                not isinstance(provider, str) or not provider.strip()
            ):
                raise ValueError("market_data_provider must be a non-empty string")
            return cls(
                position=Position(
                    side=side,
                    quantity=quantity,
                    trade_price=trade_price,
                    instrument=Instrument(
                        asset_class=asset_class,
                        symbol=symbol,
                        meta=meta,
                        current_price=current_price,
                    ),
                ),
                shock=shock,
                market_data_provider=(
                    provider.strip().upper() if provider is not None else None
                ),
            )
        except KeyError as e:
            raise ValueError(f"missing field: {e.args[0]}") from e
        except (OverflowError, TypeError) as e:
            raise ValueError(f"invalid request: {e}")
