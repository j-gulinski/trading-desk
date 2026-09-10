from dataclasses import dataclass
from decimal import Decimal
import math

from desk_domain.symbols import is_valid_symbol
from desk_domain.trade_rules import decimal_value, validate_position
from desk_domain.instruments import FinancialInstrument, instrument_for

MAX_SPOT_SHOCK = 10.0
MAX_CURVE_SHOCK_BPS = 10_000.0


@dataclass
class ScenarioRequest:
    instrument: FinancialInstrument
    side: str
    quantity: Decimal
    trade_price: Decimal
    current_price: Decimal | None
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
            symbol = inst.get("symbol", "")
            if not is_valid_symbol(symbol):
                raise ValueError("instrument.symbol must be a valid symbol")
            instrument = instrument_for(asset_class, symbol, meta)
            side = pos["side"]
            quantity, trade_price = validate_position(
                instrument, side, pos["quantity"], pos["trade_price"]
            )
            raw_current = inst.get("current_price")
            current_price = (
                decimal_value(raw_current, "current_price")
                if raw_current is not None else None
            )
            if not instrument.allows_negative_price and current_price is not None \
                    and current_price <= 0:
                raise ValueError("current_price must be greater than zero")
            shock = float(body["shock"])
            if not math.isfinite(shock):
                raise ValueError("shock must be finite")
            if instrument.needs_quote:
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
                instrument=instrument, side=side,
                quantity=quantity, trade_price=trade_price, current_price=current_price,
                shock=shock,
                market_data_provider=(
                    provider.strip().upper() if provider is not None else None
                ),
            )
        except KeyError as e:
            raise ValueError(f"missing field: {e.args[0]}") from e
        except (OverflowError, TypeError) as e:
            raise ValueError(f"invalid request: {e}")
