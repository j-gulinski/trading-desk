# Market data — provider and contract reference

Current facts only: providers, normalized contracts, feed parameters, endpoints, storage.
The reasoning behind these facts — why each boundary exists and what was rejected — lives
in the phase reports. Provider facts come from live API probes (2026-08-17, all six
providers; NBP/ECB re-verified 2026-08-23 at wiring); *verified* = seen in a live
response, *docs* = provider documentation, re-check when credentials or plans change.
Alpha Vantage is researched but not wired.

## Quote providers

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
| Symbol search | `/search` + full `/stock/symbol?exchange=US` directory | `symbol_search` — one API credit per request | `SYMBOL_SEARCH`, free *(verified)* |
| Market open/closed | `/stock/market-status`, free *(docs)* | `is_market_open` on every quote *(verified)* | static hours in search metadata |
| Error shape | proper `401`/`429` + `{"error": …}` *(verified 401)* | **HTTP 200** + `{"code":429,"status":"error"}` *(verified shape)* | **HTTP 200** + `"Information"`/`"Note"` key *(verified)* |

Session fields the quote responses already carry are part of the normalized contract as
nullable, stored-as-received extras: day open/high/low (Finnhub `o/h/l`, Twelve Data
`open/high/low`), 52-week bounds (Twelve Data `fifty_two_week`), session-cumulative share
volume and average volume (Twelve Data, where the instrument supports them). They live on
the board row, ride every tick, and render only in the Quote Detail session block — the
board table is unchanged, change-only snapshots stay price provenance, and a field a tier
does not publish renders n/a, never zero. Displayed order-book depth and derivatives open
interest remain unpublished on the wired free tiers and stay out of the contract; any
further field must name the measure, interval/as-of, units, instrument scope and
entitlement before it enters.

## Official sources

| | NBP | ECB | FRED |
| --- | --- | --- | --- |
| Data | FX fixings: table A (`mid`), **table C (`bid`/`ask`)**, gold (PLN per 1 g) | Yield curves **AAA (`G_N_A`) and all-bonds (`G_N_C`)**, tenors `SR_3M…SR_30Y`; EXR FX fixings | `DGS1MO…DGS30` Treasury curve; SOFR/DFF; **OECD Poland series** |
| Verified Mon Aug 17 | table `158/A` dated 08-17; C: bid 3.6804 / ask 3.7548; 157/C was Friday — clean business-day sequence | YC as-of 08-14 (Fri, publishes next TARGET day ~noon); EXR 08-17: USD 1.1593, PLN 4.3063 | DGS through 08-13 (1–2 business-day lag); SOFR through 08-14; **Poland monthly through 2026-06** |
| Auth / limits | none; 93-day range cap | none; fair use | free instant key; 120 req/min |
| Format note | plain JSON | **use `format=csvdata`** — SDMX-JSON nests values ~5 levels deep; CSV is stdlib-parseable | JSON; values are *strings*, missing = `"."` |

Wiring-time facts *(verified 2026-08-23, live)*:

- **NBP**: the latest-table endpoints (`/exchangerates/tables/a`, `/cenyzlota`) always
  answer `200` with the last published business-day fixing. A *date-addressed* query for a
  date with no fixing returns **HTTP 400** (not 404); the wired feed never date-addresses —
  "not published yet" is detected by the as-of not advancing, with no error path involved.
  Table A carries 32 currencies; gold is a separate endpoint quoting **PLN per 1 g** of
  1000-fineness gold.
- **ECB**: `format=csvdata` is flat and `csv.DictReader`-parseable (`KEY`, `CURRENCY`,
  `TIME_PERIOD`, `OBS_VALUE`, …). The rates are the **14:15 CET concertation** values
  (per series metadata), published ~16:00 CET. One series key covers several currencies
  (`D.USD+PLN.EUR.SP00.A`, one row each); a currency the dataset lacks is simply absent.
- EUR/PLN cross-check example (Fri 08-21): NBP `4.3122` (~11:00 fixing) vs ECB `4.3078`
  (14:15 concertation) — ~10 bps apart; the UI chip shows this spread live.
- FRED has **no NBP-equivalent Polish rate endpoint** (404 verified on NBP's side): a PLN
  curve must be assembled from FRED's OECD Poland series (`IR3TIB01PLM156N` 3M interbank,
  `IRLTLT01PLM156N` 10Y gov bond; monthly, ~2-month lag).

## Contracts

### The normalized quote

Every provider payload normalizes to one shape before anything stores or reads it
(`shared/quotes.py`, `build_quote`):

- **Prices are exactly what the provider gave** — `bid`, `ask`, `last`, each nullable,
  parsed straight to `Decimal` from the wire string. A spread is never synthesized; absent
  fields stay NULL.
- **`mid` is derived, never invented**: `(bid+ask)/2` when both sides exist, else the
  official reference mid when the source publishes one, else `last`. An unpriced quote is
  rejected at build time.
- **`price_basis`** records which case produced `mid`: `BID_ASK`, `REFERENCE_MID`, or
  `LAST`. Valuation and display headline use `mid`; spot execution uses ask for BUY / bid
  for SELL, falling back to `mid` when the provider publishes no spread.
- **`quote_grade`**: `REALTIME` (live tradable), `EOD` (daily close — Alpha Vantage
  equities), `REFERENCE` (official fixing — NBP, ECB). The grade travels with every quote.
- **Two clocks**: `provider_timestamp` (the provider's own event time, nullable) and
  `received_at` (ingest time). Age is measured on the provider's clock; ingest lag is the
  difference.

Per-provider basis mapping: Finnhub last-only; Twelve Data last-only; Alpha Vantage equity
last-only (EOD), FX true bid/ask; NBP table A = official mid, table C = official bid/ask;
ECB EXR = official mid.

### Freshness

`shared/freshness.py`, five states per (provider, symbol):

| State | Meaning |
| --- | --- |
| `LIVE` | market open: quote age (provider clock) within the threshold for that provider × asset class |
| `CLOSED` | market closed and confirmation polls still arriving — the closing price *is* the current price |
| `STALE` | the feed should be updating and is not: past the provider-clock threshold while open, or confirmation polls stopped while closed |
| `MISSING` | the provider should serve this symbol but no data has arrived |
| `UNSUPPORTED` | the provider *cannot* serve this class — a static capability fact, never confused with missing data |

The classifier is a pure function with two clocks and two regimes: market open judges the
*provider* timestamp against 3× the open cadence; market closed judges the *received*
timestamp against 3× the closed cadence — STALE means "the feed is broken" in both, and an
overnight board reads CLOSED. Every tick and snapshot row carries `market_open`,
`stale_after_seconds` and `closed_stale_after_seconds`, so `/quotes` and the UI classify
identically. The market-open flag is Finnhub's exchange-level `/stock/market-status` for
Finnhub rows and Twelve Data's per-symbol `is_market_open` for Twelve Data rows.
MISSING, UNSUPPORTED and STALE block a new trade (enforced at the ticket and the server);
a manual close may use the last stale quote so a position is never trapped by a quiet feed.

Valuations classify the same way against their trade's feed instrument: LIVE while the
mark keeps up, **MKT CLOSED** (distinct from a closed trade) while the venue is shut,
STALE when the feed breaks or pricing lags; a flat 10 s wall-clock rule survives only as
the fallback for tabs with no market data yet.

Reference rows derive freshness from the publication calendar instead of a cadence: at
store time `stale_after_seconds` = time from the fixing's as-of to the next expected
publication (next business day's window end) + 4 h grace, so a Friday fixing reads current
(the UI renders `CURRENT` for reference-grade LIVE) through the weekend; `market_open`
stays NULL. Source public holidays are not modeled — a holiday Monday reads STALE that
evening until the next real fixing arrives.

### The capability matrix

`shared/providers.py` is the registry: six providers, their group, and class-level
capability facts. An asset class absent from a provider's map *is* the UNSUPPORTED state.

| | EQUITY | FX | COMMODITY | curves |
| --- | --- | --- | --- | --- |
| FINNHUB | REALTIME | — | — | — |
| TWELVE_DATA | REALTIME | REALTIME | REALTIME | — |
| ALPHA_VANTAGE | EOD | REALTIME | — | — |
| NBP | — | REFERENCE | REFERENCE (gold) | ✓ (config proxy) |
| ECB | — | REFERENCE | — | ✓ |
| FRED | — | — | — | ✓ |

Metals re-checked 2026-08-18 with registered keys: Twelve Data serves `XAU/USD` as a
forex-style quote (so XAUUSD is tradeable via Twelve Data); Alpha Vantage rejects XAU on
`CURRENCY_EXCHANGE_RATE` while EUR→USD works — its COMMODITY cell stays UNSUPPORTED.
ETFs quote through the equity endpoints everywhere, so SPY is classed `EQUITY`. The matrix
drives the UNSUPPORTED rows in `/quotes`, provider toggles on search results, and the
ticket's N/A rows. The watchlist stores the user's *choice* of providers; capability is
answered from the registry on demand — the two are separate facts. Capability is
class-level today: a ticker one provider lists and another doesn't is discovered when its
quote never arrives (NO DATA).

### Curves

`shared/curves.py`: a `CurveSet` is (provider, curve_name, `curve_type`, currency,
optional `index_tenor`, as-of date) plus ordered `CurvePoint`s and the raw source
response for the whole set. Each point carries `source_series` (the FRED/ECB series id;
NULL marks a derived point) and `source_as_of` (always the anchor's own date — visible
when it lags the set's as-of). `index_tenor` names the floating index a projection curve
represents, so tenor-matching validation has a schema fact. `curve_type` is a small text
vocabulary: `GOV_ZERO` (government curve, par yields treated as zero rates —
documented simplification), `COMPOSITE_REF` (assembled from mixed official reference
series), `POLICY_PROXY` (flat at a configured policy rate). A set's as-of is the **oldest**
of its sources' dates — a curve is only as current as its stalest anchor, the same rule
the FX resolver applies to cross legs.

The wired catalog (latest stored set per name serves reads; history accumulates one set
per source-day):

| Curve | Source | Type | Points | As-of behavior |
| --- | --- | --- | --- | --- |
| `USD_TREASURY` | FRED, 11 `DGS*` series (1M–30Y), one request each | GOV_ZERO | 11, all sourced | daily, 1–2 business-day lag; a series whose newest value is `"."` falls back within a 7-observation lookback |
| `EUR_GOV_AAA` | ECB YC `G_N_A`, one csvdata request | GOV_ZERO | ≤11 (3M–30Y), all sourced | daily, publishes ~12:00 CET for the prior TARGET day |
| `EUR_GOV_ALL` | ECB YC `G_N_C`, one csvdata request | GOV_ZERO | ≤11, all sourced | same — the second euro curve that makes projection-vs-discount real |
| `PLN_REF` | FRED OECD `IR3TIB01PLM156N` (3M interbank) + `IRLTLT01PLM156N` (10Y gov) | COMPOSITE_REF, `index_tenor` 3M | 2 sourced anchors + 3 linearly interpolated (1Y/2Y/5Y, NULL series) | monthly, ~2-month lag; refetched weekly |
| `PLN_NBP_BASE` | `NBP_REFERENCE_RATE_PERCENT` (config — NBP publishes the rate but not via its API) | POLICY_PROXY | 5, all derived | rebuilt locally; a new set when the Warsaw date or the configured rate changes; never drives provider status |

Stored rates are the published percent values. The wire shape carries both: `points`
(percent, with per-point provenance — what the chart and inspector read) and flattened
`tenors`/`rates` arrays (years / decimal fractions — what pricing math consumes). Curve
writes are change-only per (provider, curve, as-of): a confirmation poll only advances
`received_at`; a new or revised set writes points + raw and audits `CURVE_SET_WRITTEN`.

### Symbols and the symbol master

- Canonical form: uppercase, `^[A-Z0-9][A-Z0-9_.\-]{1,31}$` (`shared/symbols.py`). FX
  pairs are six-letter `BASEQUOTE`; per-provider notation (`EUR/USD`, from/to params) is
  each client's private concern.
- The symbol master is the **`watchlist_items` table** — the user-curated universe
  (symbol, class, quote currency, chosen providers). The ticket's instrument list and
  trade-action's execution gate read it: what isn't watched isn't tradeable, capped by
  `MAX_ACTIVE_SYMBOLS`.
- The polled *active set* = watchlist ∪ open-trade symbols ∪ benchmark, reloaded from the
  DB every 15 s.

## Feeds

Module shape, identical per provider: `clients/<provider>.py` (endpoints + body rules over
`clients/base.py` transport) → `normalizer.py` → `persistence.py` (board upsert +
change-only history) → `publisher.py` (provider-tagged SSE), with one feed module per
provider and `scheduler.py` as the registry the API reads. A new provider is a client +
feed pair plus one registry line.

### Finnhub

- Classes: EQUITY (incl. ETFs). Two priority tiers:

| Tier | Who | Cadence (open) | Cadence (closed) | LIVE while (3×) |
| --- | --- | --- | --- | --- |
| 1 | open-trade symbols + `BENCHMARK_SYMBOL` | 15 s | 300 s | ≤ 45 s |
| 2 | rest of the watchlist | 60 s | 300 s | ≤ 180 s |

- Market open/closed from `/stock/market-status`, checked every 10 min; when closed all
  polling decays to the 5-minute confirmation cadence. Opening a trade promotes its symbol
  to tier 1 within one active-set reload.
- Token bucket at 90% of `FINNHUB_PROVIDER_LIMIT_PER_MINUTE` (54/min default); every
  request — quote, market status, search, manual refresh — spends one token; a daily
  ledger counts spend for the ops surface.

### Twelve Data

- Classes: EQUITY, FX, COMMODITY. Flat cadence `TWELVE_DATA_POLL_SECONDS` (15 min best
  case); the **daily ledger is what actually paces**: 90% of the 800/day cap = 720
  credits, spread across the configured 12 h active window; a poll, refresh or search runs
  only while `credits_today + cost ≤ safe budget`.
- **Batching**: one `/quote?symbol=A,B,…` call, 1 credit/symbol, chunk size = the derived
  safe minute budget (7 default). A per-symbol error inside a batch is a data error for
  that symbol only. After each batch, per-symbol due-times are staggered across the next
  interval so the board refreshes rolling rather than in lockstep.
- **Clocks**: payload `timestamp` is the day bar's open — wrong for freshness;
  `last_quote_at` is the actual quote time and is what the normalizer uses.
- **Session is per symbol** (`is_market_open` on every quote): NVDA reads CLOSED overnight
  while EUR/USD on the same provider reads LIVE. FX keeps ticking through the weekend —
  verified Sunday 2026-08-23: `"is_market_open": true`, fresh `last_quote_at`, close
  moving 4.31225 → 4.31182. That is Twelve Data's consolidated retail feed (weekend-active
  venues, indicative pricing); the board reports the provider's claim, and the
  official-rates panel beside it (frozen at Friday's as-of) is the counterweight.
- Errors arrive as HTTP 200 with `{"code": …, "status": "error"}`; `classify_body` maps
  them into the shared state machine.

### NBP and ECB

- Keyless clients (`clients/nbp.py` table A + gold; `clients/ecb.py` EXR via csvdata — it
  overrides the base `decode_body` hook to parse CSV with the stdlib). Runtimes carry the
  same status machine and cooldowns as quote providers but no token bucket and no daily
  budget (`keyless: true` on `/providers`), only a calls-today counter.
- Calendar windows, not cadences: poll every 5 min inside the source's publication window
  (NBP 11:45–12:20 Warsaw; ECB 15:55–16:45 Frankfurt, business days) until a new as-of
  appears, then hourly confirmation. A failure degrades only that provider's card
  (verified live via DNS blackhole: NBP → ERROR, everything else OK, recovery audited).
- Reference universe = configured defaults (`NBP_REFERENCE_SYMBOLS`,
  `ECB_REFERENCE_SYMBOLS`) ∪ settlement currencies of ACTIVE trades (as `<CCY>PLN` /
  `EUR<CCY>`) while the source publishes them. Full tables are not ingested as rows — each
  snapshot retains the complete raw table response.
- Rows are reference-graded, never tradeable: ordinary `build_quote` with
  `reference_mid`, grade `REFERENCE`, `provider_timestamp` = the as-of date at midnight
  UTC (the source publishes a date, not a time; the UI renders "as of 2026-08-21"). Board
  reads and SSE tag them `reference` (fourth origin flag beside watched/held/benchmark).
  Four independent guards keep them un-tradeable: watchlist validation and symbol search
  offer quote providers only, `/instruments` derives from watched ∪ held, and
  trade-action refuses a reference `market_data_provider` with the reason.
- Gold keeps its published unit: symbol `XAUPLN_G`, **PLN per 1 g** (a six-letter
  `XAUPLN` would read as per-troy-ounce, wrong by ×31.1034768); the ounce conversion is a
  documented cross-check, never a stored row.
- **History backfill**: after its first successful live round, a feed whose pair has at
  most one stored observation fetches up to `REFERENCE_BACKFILL_DAYS` (90) of history —
  NBP `tables/a/last/{n}` + `cenyzlota/last/{n}` (93-day source cap), ECB
  `lastNObservations` — and inserts change-only snapshots strictly older than anything
  stored: `provider_timestamp` = the fixing's as-of, `received_at` = the backfill moment,
  raw = that day's response slice. The drill tape then shows the published daily series;
  unlike the sparse quote tapes it is complete by construction (one fixing per business
  day, identical consecutive values excepted). A transient failure retries hourly; runs
  once per pair.

### FRED and the curve feeds

- `clients/fred.py`: key in `api_key`, `file_type=json`; observation values are strings
  with `"."` for missing; a bad/unregistered key answers **HTTP 400** naming `api_key`,
  classified as AUTH_FAILED. Budget: 108/min bucket from the published 120/min.
- Curve feeds reuse the calendar-window pattern (windows above in `configuration.md`);
  every curve also refetches on the hourly confirmation poll, so a freshly booted stack
  has all sets within one loop tick regardless of window. Manual
  `POST /curves/refresh?curve=` / `?provider=` refetches on demand within the budget.
- ECB's yield curves share the ECB runtime with the EXR fixings (one status machine,
  two loops); the NBP proxy build is local and can neither fail nor mask the fixing
  feed's health.

## The FX resolver and the reporting currency

`shared/fx.py` is the single owner of conversion. It reads the reference board rows
(NBP/ECB, class FX) and resolves `from → to` with fixed precedence:

1. **identity** — rate 1;
2. **direct official rate or its inverse** — when both sources publish the pair, the
   fresher as-of wins, tie to ECB;
3. **cross via EUR** — both legs from ECB;
4. **cross via PLN** — both legs from NBP's table A.

A path never mixes sources. Every resolution returns rate (derived rates rounded to
8 significant digits; stored mids stay exactly as published), path label, provider, as-of
(the older leg for a cross) and symbols used; "no official path" is an answer with a
reason, not an error. All arithmetic is `Decimal`.

`GET /fx/rates?to=<CCY>` serves one resolution per known currency. Conversion is a
display overlay: the browser multiplies on Valuations and Books — per-currency subtotals
stay primary; one converted total (and, on Valuations, the converted headline cards)
appears only after the user picks a reporting currency (chip row, remembered per
browser); every converted row is labeled with rate, provider and as-of; an unconvertible
currency stays a labeled subtotal with the resolver's reason. Nothing converted is ever
persisted, and no service calls another service's API for it. The browser's 60 s rate TTL
is the only cache — the gateway serves `/fx/rates` from two small indexed reads.

## Watchlist self-service and discovery

Board rows carry server-truth origin flags (`watched`/`held`/`benchmark`/`reference`);
watched rows get the remove control, held rows a POS tag, the benchmark its own summary
strip. Incapable provider/class pairs are not rendered as board rows — capability shows
where a decision is made (search toggles, ticket N/A). `_board_payload` filters to the
active set on every read; a daily sweep removes stray rows (reference rows validate
against the reference universe).

- `GET /watchlist` — items with chosen providers plus per-class provider capability (two
  separate facts).
- `POST /watchlist {symbol, asset_class, currency, providers?}` — validates canonical
  form, spot classes, `MAX_ACTIVE_SYMBOLS`; omitted `providers` = every capable provider;
  an incapable named provider is refused with the reason. Adding to an existing symbol is
  a merge, not a 409. Audit row in the same transaction; the add fires one targeted,
  budget-aware refresh per feed actually added, so the first quote lands in seconds.
- `DELETE /watchlist/<symbol>?provider=` — drops one feed or the whole symbol; answers
  `{symbol, removed_providers, remaining_providers, still_polled}`; a `market_remove` SSE
  event names exactly the (provider, symbol) rows every open tab should drop; feeds kept
  alive by a position or the benchmark stay as POS/BMK rows. History rows are untouched.
- `GET /symbols/search?q=` — Finnhub `/search` + Twelve Data `symbol_search` fetched in
  parallel, both through their provider budgets, cached 10 min per query, ranked
  exact-prefix-first, provider-tagged, results name their quote currency. The UI renders
  one row per symbol with capable providers as toggles.

The board draws no intraday trend: `market_data_snapshots` holds sparse changes observed
while this application ran, not a market series — connecting them would invent movement
through unobserved time. Selecting a row opens a newest-first tape of its latest 60 stored
changes (one DB read; re-read only on a changed tick; no polling timer, no provider
credits).

### Endpoints

| Route | Serves |
| --- | --- |
| `GET /market-data/snapshot` | the board read from the DB (warm after restart) + `stream_id` — the UI's seed |
| SSE `/market-data/stream` | `market_tick` per successful poll, provider-tagged, with `stream_id`/`event_id` |
| SSE `/market-data/stream/<provider>` | the same contract filtered to one wired provider (quote or reference); unknown/unwired provider is 404 |
| `GET /market-data/quotes` | stored active-set + reference quotes with computed freshness; filterable by `symbol`, `asset_class`, `provider` |
| `GET /market-data/quotes/<provider>/<symbol>` | one active normalized quote; unknown provider or missing row is 404 |
| `GET /market-data/quotes/<provider>/<symbol>/history?limit=&raw=` | latest stored change observations; limit 1–200; `raw=1` includes each observation's stored raw payload (the provenance drill) |
| `GET /market-data/curves?raw=` | latest stored set per curve: metadata, provenance-carrying points, pricing arrays; `raw=1` adds each set's raw source response |
| `GET /market-data/curves/<provider>?raw=` | the same filtered to one wired provider; unknown provider is 404 |
| `POST /market-data/curves/refresh?curve=&provider=` | targeted curve refetch within the provider budget; without `curve`: every curve the provider (or all providers) builds |
| `GET /fx/rates?to=<CCY>` | one resolution per known currency: rate, path, provider, as-of, or an honest no-path reason |
| `GET /watchlist` · `POST /watchlist` · `DELETE /watchlist/<symbol>?provider=` | the symbol master, self-service — offers quote providers only |
| `GET /symbols/search?q=` | provider-tagged discovery, cached 10 min |
| `GET /providers` | all six registry entries (capabilities, wired flag) + runtime for wired ones: status, budget + daily ledger, market session, active symbols, and the current poll `strategy` (what the board strip and ops card display) |
| `GET /providers/<p>/health` | one provider's runtime detail |
| `POST /market-data/refresh?symbol=&provider=` | targeted poll within budget — 404 unknown symbol, 422 unsupported class, 429 budget/pace exhausted, 503 disabled/cooldown. Without `symbol`: the provider's whole set — for NBP/ECB one keyless table refetch republishing every reference row |

The `/market-data/...` forms are canonical on port 8001; short routes remain compatibility
aliases. `/market-data/snapshot` carries the curve sets beside the spot board, and each
curve fetch publishes a `curve_tick` SSE event on the same stream (provider-filterable
like quote ticks) — pricing seeds both from the snapshot and follows both event kinds.
Every quote tick carries the full normalized quote plus `stale_after_seconds`,
`closed_stale_after_seconds`, `market_open` and the origin flags, so any consumer
classifies freshness without asking the server. Each provider HTTP call writes one
`provider_http_response` log line (request metadata, outcome, latency, `response_json`) —
the Logs view formats it on expansion.

### Error state machine (all providers)

| Signal | State | Reaction |
| --- | --- | --- |
| HTTP 429 (or body-level 429) | `RATE_LIMITED` | cooldown = `Retry-After` (default 60 s), audited |
| HTTP 401/403 (or body-level) | `AUTH_FAILED` | 5-minute cooldown, audited |
| network/timeout, 5xx | `ERROR` | 10 s backoff, log only |
| body-level data error, HTTP 404 for one symbol | per-symbol data error | log, symbol skipped this round — provider state untouched |
| next success | `OK` | audit `PROVIDER_RECOVERED` |

Cooldowns are scoped to the provider that tripped them and surface as
`cooldown_seconds_left` on the ops endpoints. `classify_body` is each client's hook for
errors that hide in 200 bodies.

## Valuation provenance — provider bound at the ticket

Pricing's cache is keyed `(provider, symbol)`; a trade is valued exclusively from its
frozen `market_data_provider`, close and final valuation included. The client chooses
provider identity; trade-action prices the fill itself from that provider's board row
(ask/bid/mid by side) and compares the client's `client_seen_price` — past
`TRADE_PRICE_TOLERANCE_PCT` the ticket is refused with the deviation. The trade records
executed price, seen price, provider, provider quote timestamp and, when that exact
observation has a retained snapshot, `entry_snapshot_id` (NULL for an unchanged
confirmation poll — never pointed at an older observation). Pre-binding rows resolve to
`DEFAULT_QUOTE_PROVIDER` and every such resolution logs `trade_provider_defaulted`.

Curve-priced classes (BOND, IRS, EUROPEAN_OPTION) execute **model-priced** through the
same gate: the ticket previews a model value via pricing `POST /price`; trade-action
recomputes the PV itself from the stored curves (`shared/curve_registry` +
`shared/pricing_math`) — plus the underlying's board row for options, which passes the
normal freshness gate on its chosen quote provider — and compares the result against
`client_seen_price` (IRS deviation is measured against notional; a zero model value skips
the check). Term validation is shared (`shared/term_schemas.validate_terms`) and enforces
the curve guards in both services identically: settlement currency must have a wired
curve, discount and projection curves must match it, and a projection curve's declared
`index_tenor` must match the leg's `floating_rate_index_tenor`. The accepted trade
freezes each curve's name, provider and as-of into its terms
(`discount_curve_as_of`, …); `price_basis` in the audit payload reads `MODEL_PV`;
`market_data_provider` stays NULL for IRS/BOND (there is no quote feed) and is the
underlying's provider for options. Valuations stamp the discount curve's provider and
as-of when no spot is involved. Close recomputes the model value from the current stored
sets of the same frozen curve names. `GET /instruments/term-schemas` answers
`{"schemas", "curves"}` — the schemas with resolved choices plus the curve catalog the
pickers and guards read.

## Storage

| Table | Role | Keying | Growth |
| --- | --- | --- | --- |
| `market_data_spot_prices` | latest quote board — what the UI, ticket and pricing read | unique (provider, symbol), upserted | bounded: one row per pair |
| `market_data_snapshots` | quote history, one row per *changed* quote, with `raw_payload` | append; indexed (provider, symbol, received_at) | ~10k rows/day worst case; swept daily past `SNAPSHOT_RETENTION_DAYS` |
| `market_data_curves` + `market_data_curve_points` | curve sets (type, raw source response) / per-point provenance | unique (provider, curve_name, as_of_date); points cascade | ≤ one set per source per day; not swept — years fit in megabytes |
| `watchlist_items` | the symbol master | symbol (primary key) | user-bounded (cap 25) |

Provenance chain: every trade carries `market_data_provider`, `entry_price_timestamp`,
`client_seen_price`, optional `entry_snapshot_id`, matching close fields; valuations stamp
provider + timestamp including the terminal row. The snapshot FKs are strict (no cascade):
the retention sweep skips rows referenced by trades, so execution provenance outlives the
window. The board carries no raw payload — history owns raw. Reference feeds add one board
row per configured pair plus gold, and change-only history means a handful of snapshot
rows per source per day, each carrying the full raw table; the one-time backfill adds up
to ~90 daily rows per pair inside the same retention window. Curve-priced trades freeze
their curve provenance in `metadata` — the drill from a trade runs trade → frozen curve
name + as-of → `market_data_curves` row → raw source response.
