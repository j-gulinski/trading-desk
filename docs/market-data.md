# Market data — providers, contracts, storage

The domain reference for the six-provider market data build. The provider fact sheets come
from live API research run against all six providers on **2026-08-17** (plan
[hw5-plan-v2.md](hw5-plan-v2.md) §2); facts are tagged *verified* (seen in a live response) or
*docs* (from documentation — re-check at key signup). This document grows with the phases:
Phase 1 added the contracts and storage sections; Phase 2 the Finnhub feed section.

## Group A — quote providers

| | Finnhub | Twelve Data | Alpha Vantage |
| --- | --- | --- | --- |
| Free budget | **60 req/min** | 8 credits/min, **800/day** (the real constraint) | **25 req/day** |
| Equity quote | `c/d/dp/h/l/o/pc/t` — last trade, unix seconds *(verified)* | `close` + `timestamp` (unix) + `last_quote_at` + `is_market_open` *(verified)* | `GLOBAL_QUOTE`: price/OHLC/volume, **date-only timestamp** *(verified)* |
| Equity bid/ask | none | none | none |
| FX | **premium only** *(docs)* | free (`EUR/USD` style) *(verified)* | free — `CURRENCY_EXCHANGE_RATE` has **real bid/ask + full datetime** *(verified)* |
| Metals (XAU) | premium | demo-blocked — verify with real key | demo-blocked — verify with real key |
| Indices (^GSPC/SPX) | premium *(docs)* | limited | premium |
| ETF (SPY) | free, real-time US *(docs)* | free | free (EOD grade) |
| Batch | none | **`symbol=A,B,…` — one HTTP call, 1 credit/symbol** *(docs; demo can't test)* | none (bulk = premium) |
| Symbol search | `/search` + full `/stock/symbol?exchange=US` directory, free | `symbol_search` — works **without a key** *(verified)* | `SYMBOL_SEARCH`, free *(verified)* |
| Market open/closed | `/stock/market-status`, free *(docs)* | `is_market_open` on every quote *(verified)* | static hours in search metadata |
| Error shape | proper `401`/`429` + `{"error": …}` *(verified 401)* | **HTTP 200** + `{"code":429,"status":"error"}` *(verified shape)* | **HTTP 200** + `"Information"`/`"Note"` key *(verified)* |

## Group B — official sources

| | NBP | ECB | FRED |
| --- | --- | --- | --- |
| Data | FX fixings: table A (`mid`), **table C (`bid`/`ask`)**, gold (PLN per 1 g) | Yield curves **AAA (`G_N_A`) and all-bonds (`G_N_C`)**, tenors `SR_3M…SR_30Y`; EXR FX fixings | `DGS1MO…DGS30` Treasury curve; SOFR/DFF; **OECD Poland series** |
| Verified Mon Aug 17 | table `158/A` dated 08-17; C: bid 3.6804 / ask 3.7548; 157/C was Friday — clean business-day sequence | YC as-of 08-14 (Fri, publishes next TARGET day ~noon); EXR 08-17: USD 1.1593, PLN 4.3063 | DGS through 08-13 (1–2 business-day lag); SOFR through 08-14; **Poland monthly through 2026-06** |
| Auth / limits | none; 93-day range cap | none; fair use | free instant key; 120 req/min |
| Format note | plain JSON | **use `format=csvdata`** — SDMX-JSON nests values ~5 levels deep; CSV is stdlib-parseable | JSON; values are *strings*, missing = `"."` |

## The ten consequences that shape the design

1. **No free Group-A source gives equity bid/ask.** Bid/ask mapping is the *main case*, not an
   edge case → the price-basis policy (D11).
2. **Alpha Vantage equities are EOD** (date-only timestamp) → every quote carries a
   `quote_grade` so the difference is explicit (D3).
3. **Twelve Data's real constraint is the daily cap** (800), not the per-minute one → the
   budget governor spreads credits across the day (D7).
4. **Finnhub has no free FX** → per-provider capability differs by asset class → the fourth
   freshness state **UNSUPPORTED**, a capability fact distinct from MISSING data (D3).
5. **The PLN curve is viable on real data**: FRED's OECD Poland series are alive —
   `IR3TIB01PLM156N` (3M interbank) and `IRLTLT01PLM156N` (10Y gov bond), monthly, ~2-month
   lag (D6).
6. **ECB serves two genuine EUR curves** → real projection-vs-discount choice; ECB×NBP FX
   cross-check agreed to <0.3% in the probes.
7. **Errors hide in 200 bodies** (Alpha Vantage `"Information"`, Twelve Data `code` field) →
   the client must classify errors from bodies, not just status codes.
8. **Benchmark: SPY on Finnhub** — indices are premium everywhere; SPY's *returns* (all
   alpha/beta needs) track the index (D14).
9. **Symbol search is free on all three** → watchlist discovery is cheap (D4).
10. **NBP has no interest-rate endpoint** (404 verified) → the PLN curve must be assembled
    from FRED's OECD Poland series (investigation write-up pending).

## Contracts (Phase 1)

### The normalized quote

Every provider payload normalizes to one shape before anything stores or reads it
(`shared/quotes.py`, produced by `build_quote`):

- **Prices are exactly what the provider gave** — `bid`, `ask`, `last`, each nullable, parsed
  straight to `Decimal` from the wire string. A spread is **never synthesized**; absent fields
  stay NULL.
- **`mid` is derived, never invented**: `(bid+ask)/2` when both sides exist, else the official
  reference mid when the source publishes one, else `last`. A quote with none of these is
  rejected at build time — an unpriced quote cannot exist.
- **`price_basis`** records which of those cases produced `mid`: `BID_ASK`, `REFERENCE_MID`,
  or `LAST`. Valuation and display headline always use `mid` (D13); execution semantics
  (BUY at ask / SELL at bid, D12) are not built yet.
- **`quote_grade`** says what kind of price this *is*: `REALTIME` (a live tradable quote),
  `EOD` (a daily close — Alpha Vantage equities), `REFERENCE` (an official fixing — NBP, ECB).
  The grade travels with every quote, so an end-of-day price is always identifiable as such.
- **Two clocks**: `provider_timestamp` (the provider's own event time, nullable — Alpha
  Vantage equities only give a date) and `received_at` (when our system ingested it). Age is
  measured from the provider's clock; ingest lag is visible as the difference.

Per-provider basis mapping: Finnhub last-only; Twelve Data last-only; Alpha Vantage equity
last-only (EOD), FX true bid/ask; NBP table A = official mid, table C = official bid/ask;
ECB EXR = official mid.

### Freshness

`shared/freshness.py` defines four states per (provider, symbol):

| State | Meaning |
| --- | --- |
| `LIVE` | quote age within the threshold for that provider × asset class |
| `STALE` | data exists but is older than the threshold |
| `MISSING` | the provider should serve this symbol but no data has arrived |
| `UNSUPPORTED` | the provider *cannot* serve this class (e.g. FX on Finnhub) — a static capability fact, never confused with missing data |

Thresholds are 2–3× each feed's *scheduled* cadence and arrive with each feed's scheduler
as configuration (Finnhub's are live at 3×); the classifier is a pure function of
(supported, timestamp, now, threshold). Policy (D3; not yet enforced at the ticket):
MISSING and UNSUPPORTED block the trade; STALE warns and requires an explicit
acknowledgement recorded in the audit trail.

### The capability matrix

`shared/providers.py` is the registry: six providers, their group, and the class-level
capability facts from the probes — which classes each provider quotes and at what grade. An
asset class absent from a provider's map *is* the UNSUPPORTED state.

| | EQUITY | FX | COMMODITY | curves |
| --- | --- | --- | --- | --- |
| FINNHUB | REALTIME | — | — | — |
| TWELVE_DATA | REALTIME | REALTIME | REALTIME | — |
| ALPHA_VANTAGE | EOD | REALTIME | — | — |
| NBP | — | REFERENCE | REFERENCE (gold) | — |
| ECB | — | REFERENCE | — | ✓ |
| FRED | — | — | — | ✓ |

Metals were demo-blocked in the 08-17 probes and re-checked with the real keys on
**2026-08-18**: Twelve Data serves `XAU/USD` ("Gold Spot / US Dollar", forex-style quote
with `is_market_open` and `last_quote_at`) — so **XAUUSD stays a tradeable symbol via
Twelve Data** (review outcome #5). Alpha Vantage rejects XAU on `CURRENCY_EXCHANGE_RATE`
(`"Error Message": "Invalid API call…"`) while the same call works for EUR→USD with real
bid/ask — a capability fact, so its COMMODITY cell stays UNSUPPORTED. NBP's gold fixing (PLN
per gram — ×31.1034768 to the troy ounce) remains the official cross-check. ETFs quote
through the same equity endpoints on all three Group-A providers, so SPY and friends are
classed `EQUITY` — no separate ETF class. The *per-symbol* matrix (which of these providers
actually quotes a given ticker) is designed to be computed once at watchlist-add and cached
on the watchlist row (D4); nothing computes it yet.

### Curves

`shared/curves.py`: a `CurveSet` is (provider, curve_name, currency, optional `index_tenor`,
as-of date) plus ordered `CurvePoint`s. Each point carries its own provenance: `source_series`
(the FRED series id / ECB key it came from; NULL marks a derived, interpolated point) and
`source_as_of` (the anchor's own date when it lags the set's as-of — the PLN composite's
monthly anchors). `index_tenor` labels what floating index a projection curve represents
(e.g. 3M), so tenor-matching validation has a schema fact to check against.

### Symbols and the symbol master

- **Canonical form**: uppercase, `^[A-Z0-9][A-Z0-9_.\-]{1,31}$` (`shared/symbols.py`). FX
  pairs are six-letter `BASEQUOTE` (`EURUSD`); per-provider notation (Twelve Data's `EUR/USD`,
  Alpha Vantage's from/to parameters) is each client's concern and ships with the clients.
- **The symbol master is the `watchlist_items` table** — the user-curated active universe
  (symbol, asset class, quote currency, cached capability matrix). It replaced the static
  `INSTRUMENT_CATALOG`: the ticket's instrument list, option-underlying choices, and
  trade-action's instrument validation all read the watchlist now. What isn't watched isn't
  tradeable — scope is a user decision, capped by `MAX_ACTIVE_SYMBOLS` (D4; the cap is not
  enforced yet).
- The polled *active set* (watchlist ∪ open-trade symbols ∪ benchmark) is the scheduler's
  concern — see the Finnhub feed section below.

## The Finnhub feed (Phase 2)

The first provider slice, and the module shape every later provider repeats (D24's
one-shape rule). The quote path: `clients/base.py` (transport + error classification) →
`clients/finnhub.py` (endpoints + body rules) → `normalizer.py` (raw payload →
`NormalizedQuote`) → `persistence.py` (board upsert + change-only history) →
`publisher.py` (provider-tagged SSE). The polling side is split by job: `active_set.py`
(the polled universe), `provider_runtime.py` (per-provider status/cooldown/budget state),
`budget.py` (token bucket + daily ledger), one feed module per provider running its
polling loop (`finnhub_feed.py`), and `scheduler.py` as the thin registry the API
endpoints read. A new provider is a client + feed pair plus one registry line.

### The active set and cadences

The scheduler polls the **active set** — watchlist ∪ open-trade symbols ∪ benchmark (D4),
reloaded from the DB every 15 s — restricted to classes Finnhub serves (EQUITY, which
includes ETFs). Two priority tiers (D7):

| Tier | Who | Cadence (open) | Cadence (closed) | LIVE while (3× cadence) |
| --- | --- | --- | --- | --- |
| 1 | open-trade symbols + `BENCHMARK_SYMBOL` | 15 s | 300 s | ≤ 45 s |
| 2 | rest of the watchlist | 60 s | 300 s | ≤ 180 s |

Market open/closed comes from Finnhub's free `/stock/market-status`, checked every 10 min;
when closed, all polling decays to the 5-minute confirmation cadence. The freshness
threshold stays at the *open* cadence, so overnight rows currently read STALE. Decision
(2026-08-19): a closed market's closing price is the current price; a separate CLOSED
display state is scoped in the plan (Phase 3a). Opening a trade promotes its symbol to
tier 1 within one active-set reload.

### Budget and the error state machine

A token bucket caps requests at `FINNHUB_BUDGET_PER_MINUTE` (48 = ~80% of the free 60/min);
every request — quote, market status, manual refresh — spends one token, and a daily ledger
counts spend for the ops surface. Errors classify into a provider state machine, never
generic failures:

| Signal | State | Reaction |
| --- | --- | --- |
| HTTP 429 | `RATE_LIMITED` | cooldown = `Retry-After` (default 60 s), audit `PROVIDER_RATE_LIMITED` |
| HTTP 401/403 | `AUTH_FAILED` | 5-minute cooldown, audit `PROVIDER_AUTH_FAILED` |
| network/timeout, 5xx | `ERROR` | 10 s backoff, log only |
| body-level error (`{"error": …}`, `c: 0`) | per-symbol data error | log, symbol skipped this round — provider state untouched |
| next success after any of the above | `OK` | audit `PROVIDER_RECOVERED` |

Cooldowns are scoped to the provider that tripped them (D7) and are visible as
`cooldown_seconds_left` on the ops endpoints. The body-level row exists because errors hide
in 200 bodies on two of the registered providers (consequence 7 above); `classify_body` is
each client's hook for exactly that.

### Endpoints

| Route | Serves |
| --- | --- |
| `GET /snapshot` | the board read from the DB (warm after restart) + `stream_id` — the UI's seed |
| SSE `/stream` | `market_tick` per successful poll, provider-tagged, with `stream_id`/`event_id` |
| `GET /quotes` | board rows + computed freshness state (LIVE/STALE) |
| `GET /providers` | all six registry entries (capabilities, wired flag) + runtime for wired ones: status, budget, market session, active symbols |
| `GET /providers/<p>/health` | one provider's runtime detail |
| `POST /refresh?symbol=` | targeted poll within budget — 404 unknown symbol, 422 unsupported class, 429 budget exhausted, 503 disabled/cooldown |

Every tick carries the full normalized quote (bid/ask/last/mid, basis, grade, both clocks)
plus `stale_after_seconds`, so any consumer can classify freshness without asking the server.

### Valuation provenance (interim rule)

Pricing's cache is keyed `(provider, symbol)`; a trade is valued exclusively from its frozen
`market_data_provider` (D13). Nothing writes that column at execution yet, so every trade
falls back to `FINNHUB` (`DEFAULT_QUOTE_PROVIDER` in pricing) — exact while Finnhub is the
only wired provider. Every valuation row is already stamped with the provider and the
provider's own quote timestamp actually used.

## Storage

| Table | Role | Keying | Growth |
| --- | --- | --- | --- |
| `market_data_spot_prices` | latest quote board — what the UI, ticket and pricing read | unique (provider, symbol), upserted | bounded: one row per pair |
| `market_data_snapshots` | quote history, one row per *changed* quote, with `raw_payload` | append; indexed (provider, symbol, received_at) | ~10k rows/day worst case; swept daily past `SNAPSHOT_RETENTION_DAYS` |
| `market_data_curves` + `market_data_curve_points` | assembled curve sets / per-point provenance | unique (provider, curve_name, as_of_date); points cascade with their set | ≤ one set per source per day by construction |
| `watchlist_items` | the symbol master | symbol (primary key) | user-bounded (cap 25) |

Provenance chain (D2): the schema gives every trade `market_data_provider`,
`entry_price_timestamp`, `client_seen_price`, and `entry_snapshot_id` — a foreign key to the
exact history row used at execution, one join from any trade to the provider's raw payload;
nothing writes these at execution yet. Valuations stamp
`market_data_provider` + `market_data_timestamp` so PnL provably follows the trade's frozen
provider. The board itself carries no raw payload — history owns raw; the board is the
read-optimized latest state.

The `entry_snapshot_id` FK is deliberately strict (no cascade): the retention sweep skips
snapshot rows referenced by trades, so referenced raw payloads outlive the retention window.

Growth math at the 25-symbol cap: Finnhub ≤ ~10k history rows/day worst case, Twelve Data
≤ 800, Alpha Vantage ≤ 25, curves ≤ ~40 points/day — trivial for Postgres and flat under
retention.
