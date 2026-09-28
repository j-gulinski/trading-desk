import subprocess
import time
import uuid
from datetime import datetime, time as day_time, timezone
from decimal import Decimal

import psycopg
from sqlalchemy import insert
from sqlalchemy.engine import make_url

from desk_day.universe import (
    BOND_BOOK, BOND_CURVE, CURRENCY, EQUITY_BOOKS, HELD_COUNT, HELD_SYMBOLS, IRS_BOOK,
    IRS_CURVE, MARKET, OPTION_BOOK, OPTION_CURVE, SYMBOLS, TRANSFER_BOOKS, company_name,
    initial_price,
)
from desk_domain.contract_data import split_terms
from desk_domain.curve_registry import latest_curve_sets, load_curve
from desk_domain.curves import (
    GOVERNMENT_BONDS, INTEREST_RATE_SWAPS, build_curve_point, build_curve_set, curve_currency,
    curve_provider,
)
from desk_domain.instruments import Bond, Equity, EuropeanOption, InterestRateSwap, instrument_for
from desk_domain.models import Book, Instrument, Trade, WatchlistItem
from desk_domain.providers import FINNHUB
from desk_domain.symbols import model_contract_symbol, watchlist_spot_catalog
from desk_domain.term_schemas import validate_terms
from desk_pricing.provenance import pricing_provenance
from desk_runtime.config import BENCHMARK_SYMBOL, env_required
from desk_runtime.db import engine, session_scope
from desk_runtime.functions import utcnow
from market_data_service.curve_store import store_curve_set

TENORS = (
    ("3M", "0.25"), ("6M", "0.5"), ("1Y", "1"), ("2Y", "2"), ("3Y", "3"), ("5Y", "5"),
    ("7Y", "7"), ("10Y", "10"), ("15Y", "15"), ("20Y", "20"), ("30Y", "30"),
)
CURVE_POINTS = {
    BOND_CURVE: (GOVERNMENT_BONDS, (
        "1.92", "1.95", "1.98", "2.05", "2.13", "2.30", "2.47", "2.68", "2.90", "3.00", "3.02",
    )),
    IRS_CURVE: (INTEREST_RATE_SWAPS, (
        "1.95", "1.97", "2.00", "2.08", "2.15", "2.30", "2.43", "2.60", "2.78", "2.85", "2.83",
    )),
    OPTION_CURVE: (INTEREST_RATE_SWAPS, (
        "4.05", "3.95", "3.80", "3.62", "3.58", "3.62", "3.72", "3.88", "4.05", "4.12", "4.05",
    )),
}
EQUITY_BOOK_TRADES = 692
TRANSFER_BOOK_TRADES = 20
MODEL_BOOK_TRADES = 500
MATURITIES = (2, 3, 5, 7, 10, 15, 20, 30)


def bond_terms(i):
    return {
        "settlement_currency": "EUR", "face_value": (1, 2, 5, 10)[i % 4] * 1_000_000,
        "coupon_rate": 1 + i % 13 * 0.25, "maturity_years": MATURITIES[i % 8],
        "payments_per_year": 1 + i % 2, "discount_curve": BOND_CURVE,
    }


def irs_terms(i):
    return {
        "direction": ("PAY_FIXED_RECEIVE_FLOAT", "RECEIVE_FIXED_PAY_FLOAT")[i % 2],
        "settlement_currency": "EUR", "notional": (5, 10, 25, 50)[i % 4] * 1_000_000,
        "fixed_rate": round(2 + i % 11 * 0.1, 2), "maturity_years": MATURITIES[i % 8],
        "floating_rate_index_tenor": ("3M", "6M")[i // 2 % 2], "discount_curve": IRS_CURVE,
    }


def option_terms(i):
    underlying = HELD_SYMBOLS[i * 7 % HELD_COUNT]
    return {
        "model": "BLACK_SCHOLES", "underlying_symbol": underlying,
        "option_type": ("CALL", "PUT")[i % 2],
        "strike": round(initial_price(underlying) * (0.8 + i % 5 * 0.1), 2),
        "maturity_years": (0.25, 0.5, 1, 2)[i % 4], "discount_curve": OPTION_CURVE,
    }


MODEL_BOOKS = (
    (BOND_BOOK, Bond, bond_terms),
    (IRS_BOOK, InterestRateSwap, irs_terms),
    (OPTION_BOOK, EuropeanOption, option_terms),
)


def maintenance_connection():
    url = make_url(env_required("DATABASE_URL")).set(drivername="postgresql", database="postgres")
    return psycopg.connect(url.render_as_string(hide_password=False), autocommit=True)


def recreate_database(name):
    with maintenance_connection() as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(f"ALTER DATABASE {name} IS_TEMPLATE false")
            conn.execute(f"DROP DATABASE {name} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {name}")
    subprocess.run(["alembic", "-c", "/app/alembic.ini", "upgrade", "head"], check=True)


def store_curves(now):
    for name, (basis, rates) in CURVE_POINTS.items():
        points = [build_curve_point(label, years, rate) for (label, years), rate in zip(TENORS, rates)]
        store_curve_set(build_curve_set(
            provider=curve_provider(name), curve_name=name, curve_basis=basis,
            currency=curve_currency(name), as_of_date=now.date(), received_at=now,
            points=points, raw_payload={"source": "desk_day seed"},
        ))


def trade_row(trade_id, book_id, instrument_id, quantity, price, currency, provider, priced_at,
              metadata, now):
    return {
        "trade_id": trade_id, "book_id": book_id, "instrument_id": instrument_id, "side": "BUY",
        "quantity": quantity, "trade_price": price, "trade_currency": currency,
        "status": "ACTIVE", "opened_at": now, "source": "SEED",
        "market_data_provider": provider, "entry_price_timestamp": priced_at,
        "client_seen_price": price, "trade_metadata": metadata,
        "created_at": now, "updated_at": now,
    }


def insert_equities(session, now):
    rows = [
        {"instrument_id": uuid.uuid4(), "symbol": sym, "name": company_name(sym),
         "asset_class": Equity.asset_class, "currency": CURRENCY, "market": MARKET,
         "terms": {}, "created_at": now}
        for sym in (*SYMBOLS, BENCHMARK_SYMBOL)
    ]
    session.execute(insert(Instrument), rows)
    session.execute(insert(WatchlistItem), [
        {"instrument_id": row["instrument_id"], "providers": {FINNHUB: True}, "created_at": now}
        for row in rows
    ])
    return {row["symbol"]: row["instrument_id"] for row in rows}


def insert_books(session, now):
    classes = {
        **{name: Equity.asset_class for name in (*EQUITY_BOOKS, *TRANSFER_BOOKS)},
        BOND_BOOK: Bond.asset_class, IRS_BOOK: InterestRateSwap.asset_class,
        OPTION_BOOK: EuropeanOption.asset_class,
    }
    rows = [
        {"book_id": uuid.uuid4(), "name": name, "expected_asset_class": asset_class,
         "created_at": now, "updated_at": now}
        for name, asset_class in classes.items()
    ]
    session.execute(insert(Book), rows)
    return {row["name"]: row["book_id"] for row in rows}


def spot_trades(books, equities, now):
    metadata = split_terms(instrument_for(Equity.asset_class, "", {"currency": CURRENCY})).metadata()
    book_names = [name for name in EQUITY_BOOKS for _ in range(EQUITY_BOOK_TRADES)]
    book_names += [name for name in TRANSFER_BOOKS for _ in range(TRANSFER_BOOK_TRADES)]
    trades = []
    for i, name in enumerate(book_names):
        sym = HELD_SYMBOLS[i % HELD_COUNT]
        trades.append(trade_row(
            uuid.uuid4(), books[name], equities[sym], 10 + i * 37 % 491,
            Decimal(str(initial_price(sym))), CURRENCY, FINNHUB, now, metadata, now,
        ))
    return trades


def price_contract(kind, terms, trade_id, curves):
    instrument = instrument_for(kind.asset_class, "", terms)
    instrument.symbol = model_contract_symbol(instrument, trade_id)
    curve = curves[instrument.discount_curve]
    underlying = instrument.quote_symbol
    spot = {"mid": Decimal(str(initial_price(underlying)))} if underlying else {}
    price = instrument.price({"curve": curve, "spot": spot})["price"]
    instrument.extras.update({
        "pricing_provenance": pricing_provenance(instrument.model, curve, instrument.maturity_years),
        "discount_curve_provider": curve["provider"],
        "discount_curve_as_of": curve["as_of_date"],
    })
    return instrument, price


def model_trades(session, books, equities, now):
    spot_catalog = watchlist_spot_catalog(session)
    curve_sets = latest_curve_sets(session)
    curves = {name: load_curve(name, session=session) for name in CURVE_POINTS}
    as_of_midnight = datetime.combine(now.date(), day_time(0), tzinfo=timezone.utc)
    instruments, trades = [], []
    for book_name, kind, terms_for in MODEL_BOOKS:
        for i in range(MODEL_BOOK_TRADES):
            terms, error = validate_terms(kind.asset_class, terms_for(i), spot_catalog, curve_sets)
            if error is not None:
                raise ValueError(f"{book_name} trade {i}: {error}")
            trade_id = uuid.uuid4()
            instrument, price = price_contract(kind, terms, trade_id, curves)
            underlying = instrument.quote_symbol
            data = split_terms(instrument)
            instrument_id = uuid.uuid4()
            instruments.append({
                "instrument_id": instrument_id, "symbol": instrument.symbol,
                "asset_class": kind.asset_class, "currency": instrument.currency,
                "terms": data.terms, "underlying_instrument_id": equities.get(underlying),
                "created_at": now,
            })
            trades.append(trade_row(
                trade_id, books[book_name], instrument_id, kind.fixed_quantity or 1 + i % 20,
                price, instrument.currency, FINNHUB if underlying else None,
                now if underlying else as_of_midnight, data.metadata(), now,
            ))
    return instruments, trades


def main():
    started = time.monotonic()
    name = make_url(env_required("DATABASE_URL")).database
    recreate_database(name)
    now = utcnow()
    store_curves(now)
    with session_scope() as session:
        equities = insert_equities(session, now)
        books = insert_books(session, now)
        instruments, models = model_trades(session, books, equities, now)
        trades = spot_trades(books, equities, now) + models
        session.execute(insert(Instrument), instruments)
        session.execute(insert(Trade), trades)
    engine.dispose()
    with maintenance_connection() as conn:
        conn.execute(f"ALTER DATABASE {name} IS_TEMPLATE true")
    print(
        f"{name}: {len(equities)} watched equities, {len(books)} books, {len(trades)} trades, "
        f"{len(CURVE_POINTS)} curves in {time.monotonic() - started:.1f} s"
    )


if __name__ == "__main__":
    main()
