# Market data — providers, contracts, storage

The current runtime wires Finnhub and Twelve Data. The provider fact sheets below also retain
research for four possible future adapters; those providers are not presented as implemented.
The research came from live API checks run against all six providers on **2026-08-17**
([implementation-roadmap.md](implementation-roadmap.md) §2); facts are tagged *verified* (seen in a live response) or
*docs* (from provider documentation — re-check when credentials or plans change). The rest
of this document describes the current contracts, feeds and storage model.

## Group A — quote providers

| | Finnhub | Twelve Data | Alpha Vantage |
| --- | --- | --- | --- |
| Free budget | **60 req/min** | 8 credits/min, **800/day** (the real constraint) | **25 req/day** |
| Equity quote | `c/d/dp/h/l/o/pc/t` — last trade, unix seconds *(verified)* | `close` + `timestamp` (unix) + `last_quote_at` + `is_market_open` *(verified)* | `GLOBAL_QUOTE`: price/OHLC/volume, **date-only timestamp** *(verified)* |
| Equity bid/ask | none | none | none |
| FX | **premium only** *(docs)* | free (`EUR/USD` style) *(verified)* | free — `CURRENCY_EXCHANGE_RATE` has **real bid/ask + full datetime** *(verified)* |
| Metals (XAU) | premium | free `XAU/USD` quote *(verified with registered key)* | unsupported by FX endpoint *(verified)* |
| Indices (^GSPC/SPX) | premium *(docs)* | limited | premium |
| ETF (SPY) | free, real-time US *(docs)* | free | free (EOD grade) |
| Batch | none | **`symbol=A,B,…` — one HTTP call, 1 credit/symbol** *(docs)* | none (bulk = premium) |
| Symbol search | `/search` + full `/stock/symbol?exchange=US` directory | `symbol_search` — one API credit per request in the current provider documentation | `SYMBOL_SEARCH`, free *(verified)* |
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
9. **Symbol search still consumes provider capacity** → results are cached for ten minutes,
   and both wired searches pass through their provider budget (D4).
10. **NBP has no interest-rate endpoint** (404 verified) → the PLN curve must be assembled
    from FRED's OECD Poland series.

## Contracts

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
  or `LAST`. Valuation and display headline always use `mid` (D13). Spot execution uses ask
  for BUY and bid for SELL, falling back to `mid` when a provider publishes no spread (D12).
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

`shared/freshness.py` defines five states per (provider, symbol):

| State | Meaning |
| --- | --- |
| `LIVE` | market open: quote age (provider clock) within the threshold for that provider × asset class |
| `CLOSED` | market closed and confirmation polls still arriving — the closing price *is* the current price, rendered neutral |
| `STALE` | the feed should be updating and is not: past the provider-clock threshold while open, or confirmation polls stopped while closed |
| `MISSING` | the provider should serve this symbol but no data has arrived |
| `UNSUPPORTED` | the provider *cannot* serve this class (e.g. FX on Finnhub) — a static capability fact, never confused with missing data |

The classifier is a pure function with two clocks and two regimes: market open
(or unknown, treated as open) judges the *provider* timestamp against 3× the open cadence;
market closed judges the *received* timestamp against 3× the closed cadence — so STALE means
"the feed is broken" in both regimes, and an overnight board reads CLOSED, not falsely
broken. Every tick and snapshot row carries `market_open`, `stale_after_seconds`, and
`closed_stale_after_seconds`, so `/quotes` and the UI classify identically and rows stay
self-classifying. The market-open flag is Finnhub's exchange-level `/stock/market-status`
for Finnhub rows and Twelve Data's per-symbol `is_market_open` for Twelve Data rows.
Policy (D3, enforced at the ticket and server): MISSING, UNSUPPORTED and STALE
block a new trade. The provider row cannot be selected and trade-action refuses a forged
intent with the reason. A manual close may use the last stale quote so an existing position
is not trapped by a quiet feed.

Valuations inherit the same honesty: a valuation classifies against its trade's feed
instrument — LIVE while the mark keeps up with the feed's newest tick within one freshness
window, **MKT CLOSED** (a distinct state, never confused with a closed trade) while the
venue is shut, STALE when the feed is broken or pricing lags it. A flat 10 s wall-clock rule
survives only as the fallback for tabs with no market data yet.

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

Metals were re-checked with registered keys on **2026-08-18**: Twelve Data serves `XAU/USD`
("Gold Spot / US Dollar", forex-style quote
with `is_market_open` and `last_quote_at`) — so **XAUUSD stays a tradeable symbol via
Twelve Data**. Alpha Vantage rejects XAU on `CURRENCY_EXCHANGE_RATE`
(`"Error Message": "Invalid API call…"`) while the same call works for EUR→USD with real
bid/ask — a capability fact, so its COMMODITY cell stays UNSUPPORTED. NBP's gold fixing (PLN
per gram — ×31.1034768 to the troy ounce) remains the official cross-check. ETFs quote
through the same equity endpoints on all three Group-A providers, so SPY and friends are
classed `EQUITY` — no separate ETF class. The class-level matrix drives the UNSUPPORTED rows in `/quotes`, the provider toggles on
search results, and the ticket's provider comparison (a provider that cannot serve the class
reads N/A there, with the reason). The watchlist row does not cache the
matrix: it stores the user's **choice** of providers, and capability is answered from the
registry on demand — the two had been conflated, which is why dropping one feed dropped
both. Refining capability to *per-symbol* facts (a ticker one provider lists and another
doesn't) is still open; today an unlistable ticker is discovered when its quote never
arrives and the pair reads NO DATA.

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
  (symbol, asset class, quote currency, and the providers chosen to poll it). It replaced the
  static `INSTRUMENT_CATALOG`: the ticket's instrument list, option-underlying choices, and
  trade-action's execution gate all read it now. What isn't watched isn't tradeable — scope is
  a user decision, capped by `MAX_ACTIVE_SYMBOLS` (D4, enforced on add).
  The watchlist is self-service: CRUD endpoints on market-data-service plus
  provider-backed symbol search (see the watchlist section below).
- The polled *active set* (watchlist ∪ open-trade symbols ∪ benchmark) is the scheduler's
  concern — see the Finnhub feed section below.

## The Finnhub feed

The first provider slice, and the module shape every later provider repeats (D24's
one-shape rule). The quote path: `clients/base.py` (transport + error classification) →
`clients/finnhub.py` (endpoints + body rules) → `normalizer.py` (raw payload →
`NormalizedQuote`) → `persistence.py` (board upsert + change-only history) →
`publisher.py` (provider-tagged SSE). The polling side is split by job: `active_set.py`
(the polled universe), `provider_runtime.py` (per-provider status/cooldown/budget state),
`budget.py` (token bucket + daily ledger), one feed module per provider running its
polling loop (`finnhub_feed.py`, `twelve_data_feed.py`), and `scheduler.py` as the thin
registry the API endpoints read. A new provider is a client + feed pair plus one registry
line. Twelve Data uses the same module boundary.

### The active set and cadences

The scheduler polls the **active set** — watchlist ∪ open-trade symbols ∪ benchmark (D4),
reloaded from the DB every 15 s — restricted to classes Finnhub serves (EQUITY, which
includes ETFs). Two priority tiers (D7):

| Tier | Who | Cadence (open) | Cadence (closed) | LIVE while (3× cadence) |
| --- | --- | --- | --- | --- |
| 1 | open-trade symbols + `BENCHMARK_SYMBOL` | 15 s | 300 s | ≤ 45 s |
| 2 | rest of the watchlist | 60 s | 300 s | ≤ 180 s |

Market open/closed comes from Finnhub's free `/stock/market-status`, checked every 10 min;
when closed, all polling decays to the 5-minute confirmation cadence and rows classify
CLOSED for as long as those confirmation polls keep landing (3× 300 s on the
received clock). Opening a trade promotes its symbol to tier 1 within one active-set
reload.

### Budget and the error state machine

A token bucket caps requests at 90% of `FINNHUB_PROVIDER_LIMIT_PER_MINUTE`
(54 of the default free 60/min);
every request — quote, market status, search, manual refresh — spends one token, and a daily ledger
counts spend for the ops surface. Errors classify into a provider state machine, never
generic failures:

| Signal | State | Reaction |
| --- | --- | --- |
| HTTP 429 | `RATE_LIMITED` | cooldown = `Retry-After` (default 60 s), audit `PROVIDER_RATE_LIMITED` |
| HTTP 401/403 | `AUTH_FAILED` | 5-minute cooldown, audit `PROVIDER_AUTH_FAILED` |
| network/timeout, 5xx | `ERROR` | 10 s backoff, log only |
| body-level error (`{"error": …}`, `c: 0`) or HTTP 404 | per-symbol data error | log, symbol skipped this round — provider state untouched |
| next success after any of the above | `OK` | audit `PROVIDER_RECOVERED` |

Cooldowns are scoped to the provider that tripped them (D7) and are visible as
`cooldown_seconds_left` on the ops endpoints. The body-level row exists because errors hide
in 200 bodies on two of the registered providers (consequence 7 above); `classify_body` is
each client's hook for exactly that.

## The Twelve Data feed

The second provider, same module shape: `clients/twelve_data.py` + `twelve_data_feed.py` +
one `scheduler.py` registry line. What differs from Finnhub is exactly what the probes said
would differ:

- **Batching.** One `/quote?symbol=A,B,…` call quotes many symbols at one credit each; the
  feed polls the whole due set in chunks of the derived safe minute budget (7 by default), so a full
  chunk fits the minute bucket. A single-symbol call returns the quote object bare; a batch
  returns a dict keyed by provider symbol — the feed normalizes both, and a per-symbol error
  object inside a batch is a data error for that symbol only, never provider state.
- **The daily-ledger governor (D7).** The binding constraint is 800 credits/*day*. The
  shared 90% safety setting derives a 720-credit hard ledger, and cadence spreads that
  allowance across the configured 12-hour active window. A poll or manual refresh only runs
  while `credits_today + cost ≤ safe daily budget`; the ledger and both provider/safe limits
  are surfaced on `/providers`. A symbol-search call also reserves and records one credit.
- **Symbol notation is the client's concern.** Internal `EURUSD`/`XAUUSD` map to the wire's
  `EUR/USD`/`XAU/USD` inside the client (6-letter FX/COMMODITY symbols split 3/3); nothing
  outside the client ever sees provider notation.
- **Two timestamps in the payload.** `timestamp` is the day bar's open — the *wrong* clock
  for freshness (it made fresh quotes read 17 h old); `last_quote_at` is the actual quote
  time and is what the normalizer uses, falling back to `timestamp` when absent.
- **Market session is per symbol.** Every quote carries `is_market_open`; the feed remembers
  it per symbol, so NVDA reads CLOSED overnight while EUR/USD on the same provider reads
  LIVE — there is no provider-level session for a provider that quotes three asset classes.
- **Errors arrive as HTTP 200** with `{"code": …, "status": "error"}`; `classify_body` maps
  code 429 → `RATE_LIMITED`, 401/403 → `AUTH_FAILED`, the rest → data errors. The state
  machine and cooldown semantics are Finnhub's, unchanged.

Cadence is flat (no tiers): every supported symbol every `TWELVE_DATA_POLL_SECONDS` (15 min),
best case — the daily governor is what actually paces a large watchlist. The freshness
threshold is 3× that cadence in both regimes, since closed-market confirmation polls run at
the same rate.

## Watchlist self-service and discovery

The quote table shows watchlist/open-position rows; the configured benchmark has its own
summary strip above the filters instead of appearing as another quote row. Every row carries
server-truth origin flags (`watched` / `held` / `benchmark`) saying why it is there: watched
rows get the remove control and held rows a POS tag (a position anchors them). Rows with data
classify LIVE/CLOSED/STALE; a watched pair with no data yet renders MISSING. Provider
capability remains available in the watchlist metadata, but incapable provider/class pairs
are **not rendered on the board**. Capability facts appear where a decision is made: as toggles in search results
and as an N/A row on the ticket's provider comparison, not as permanent dash rows on the
board. `_board_payload` filters to the active set on every read and a
daily sweep deletes stray spot rows, so a symbol that leaves the active set by any route — a
closed trade, a poll racing a removal — leaves the board with it.

- `GET /watchlist` — items with the providers **chosen** for each symbol, plus what each
  wired provider is *capable* of for that class. The two are separate facts.
- `POST /watchlist {symbol, asset_class, currency, providers?}` — validates against the
  canonical form, the spot classes, and `MAX_ACTIVE_SYMBOLS`; an omitted `providers` list
  means every provider that can quote the class, and a named provider that cannot is
  refused with the reason. Adding a provider to a symbol already watched is a **merge**
  (`WATCHLIST_PROVIDER_ADDED`), not a 409. The audit row is written in the same transaction;
  then every feed's active set reloads, so the first quote lands within seconds rather than
  at the next 15 s reload.
- `DELETE /watchlist/<symbol>?provider=` — drops one feed and leaves the others polling;
  without the parameter it removes the symbol. Audited (`WATCHLIST_PROVIDER_REMOVED` /
  `WATCHLIST_SYMBOL_REMOVED`) and answered
  `200 {symbol, removed_providers, remaining_providers, still_polled}`. Board rows for feeds
  nothing else claims are deleted and a `market_remove` SSE event names those
  `(provider, symbol)` rows so every open tab drops exactly them; feeds an open position or
  the benchmark keeps alive land in `still_polled` and their rows stay put as POS/BMK rows.
  History rows are untouched (provenance).
- `GET /symbols/search?q=` — discovery across providers (D4): Finnhub `/search` (US
  equities; costs one budget token, skipped silently when the bucket is empty) merged with
  Twelve Data `symbol_search` (equities, FX, metals; one recorded request credit), the two fetched in
  parallel so the response costs one provider round-trip, not two. Results are
  provider-tagged, normalized to internal symbols, ranked exact-prefix-first, and cached
  for 10 minutes per query so typing doesn't drain budgets. The UI groups them one row per
  *symbol* with the capable providers as **toggles**: providers already on the board are
  ticked and disabled, the rest are the choice, and the Add button counts what it will
  create. A provider filter beside the board search narrows the watchlist without changing
  provider membership.

`GET /history` returns the current UTC day's locally observed changes (the latest point in
each five-minute bucket) and ends at the current board value. Previous close remains the
separate basis for Change today; plotting it at midnight created a false diagonal through
hours with no observation. The compact trend opens a detail panel with observation times,
high/low, previous close, and recent values. History is filtered to the active set and capped at 300
`[epoch_ms, mid]` points per (provider, symbol). There is no provider backfill or multi-day
selector.

### Endpoints

| Route | Serves |
| --- | --- |
| `GET /snapshot` | the board read from the DB (warm after restart) + `stream_id` — the UI's seed |
| SSE `/stream` | `market_tick` per successful poll, provider-tagged, with `stream_id`/`event_id` |
| `GET /quotes` | stored active-set quotes + computed freshness state; filterable by `symbol`, `asset_class`, `provider` |
| `GET /watchlist` · `POST /watchlist` · `DELETE /watchlist/<symbol>?provider=` | the symbol master, self-service and per provider |
| `GET /symbols/search?q=` | provider-tagged discovery, cached 10 min |
| `GET /history` | observed Today mid series per (provider, symbol) |
| `GET /providers` | all six registry entries (capabilities, wired flag) + runtime for wired ones: status, budget + daily ledger, market session, active symbols, and the current poll `strategy` (mode, cadences, server-composed description — what the board strip and the ops card display) |
| `GET /providers/<p>/health` | one provider's runtime detail |
| `POST /refresh?symbol=&provider=` | targeted poll within budget (provider defaults to FINNHUB) — 404 unknown symbol, 422 unsupported class, 429 budget/pace exhausted, 503 disabled/cooldown |

Every tick carries the full normalized quote (bid/ask/last/mid, basis, grade, both clocks,
`previous_close`) plus
`stale_after_seconds`, `closed_stale_after_seconds`, `market_open`, and the origin flags,
so any consumer can classify freshness without asking the server. SSE also carries
`market_remove` (symbols leaving the board) alongside `market_tick`.

Each provider HTTP call writes one `provider_http_response` line containing request metadata,
outcome, latency, and `response_json`. The Logs view formats that raw JSON on expansion. A
404 returned for one searched/watched symbol remains a data error and does not change the
provider-wide health state.

### Valuation provenance — provider bound at the ticket

Pricing's cache is keyed `(provider, symbol)`; a trade is valued exclusively from its frozen
`market_data_provider` (D13), close path and final valuation included. The provider column
is written by the execution gate, while the client only chooses provider identity:
opening a spot trade requires a
provider that is actually polling the symbol, and trade-action prices the fill itself from
that provider's board row — the ask for a BUY, the bid for a SELL, the mid when the feed
quotes no spread. The client's number arrives as `client_seen_price` and is only compared:
past `TRADE_PRICE_TOLERANCE_PCT` the ticket is refused with the deviation in the message.
The trade row records the executed price, the seen price, the provider, the provider's quote
timestamp and, when that exact board observation has a retained change snapshot,
`entry_snapshot_id`. The foreign key is left NULL for an unchanged confirmation poll rather
than pointing at an older observation; referenced snapshots are never swept. Rows written
before binding existed still
resolve to `DEFAULT_QUOTE_PROVIDER` (FINNHUB), and every such resolution logs
`trade_provider_defaulted`.

Curve-priced classes (BOND, IRS, EUROPEAN_OPTION) have no wired source, so trade-action
refuses new positions in them with the reason rather than booking something nothing can
value; existing rows stay open and blocked.

## Storage

| Table | Role | Keying | Growth |
| --- | --- | --- | --- |
| `market_data_spot_prices` | latest quote board — what the UI, ticket and pricing read | unique (provider, symbol), upserted | bounded: one row per pair |
| `market_data_snapshots` | quote history, one row per *changed* quote, with `raw_payload` | append; indexed (provider, symbol, received_at) | ~10k rows/day worst case; swept daily past `SNAPSHOT_RETENTION_DAYS` |
| `market_data_curves` + `market_data_curve_points` | assembled curve sets / per-point provenance | unique (provider, curve_name, as_of_date); points cascade with their set | ≤ one set per source per day by construction |
| `watchlist_items` | the symbol master | symbol (primary key) | user-bounded (cap 25) |

Provenance chain (D2): the schema gives every trade `market_data_provider`,
`entry_price_timestamp`, `client_seen_price`, and an optional `entry_snapshot_id`. The
snapshot foreign key is written only when the board still represents that exact stored
observation. Close stores the corresponding `close_price_timestamp` and optional
`close_snapshot_id`. Valuations stamp `market_data_provider` + `market_data_timestamp`,
including the terminal row, so PnL provably follows the trade's frozen provider. The board
itself carries no raw payload — history owns raw; the board is the read-optimized latest
state.

The entry and close snapshot FKs are deliberately strict (no cascade): the retention sweep
skips snapshot rows referenced by trades, so referenced raw payloads outlive the retention
window.

Growth math at the 25-symbol cap: Finnhub ≤ ~10k history rows/day worst case, Twelve Data
≤ 800, Alpha Vantage ≤ 25, curves ≤ ~40 points/day — trivial for Postgres and flat under
retention.
