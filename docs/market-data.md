# Market data — provider and contract reference

Current facts only: providers, normalized contracts, feed parameters, endpoints, storage.
The reasoning behind these facts — why each boundary exists and what was rejected — lives
in the phase reports. Provider facts come from live API probes (2026-08-17 through
2026-08-26, all seven providers); *verified* = seen in a live
response, *docs* = provider documentation, re-check when credentials or plans change.

## Quote providers

| | Finnhub | Twelve Data | Alpha Vantage |
| --- | --- | --- | --- |
| Free budget | **60 req/min** | 8 credits/min, **800/day** (the real constraint) | **25 calls/day**; application safe cap 22 plus ≥15 s spacing |
| Equity quote | `c/d/dp/h/l/o/pc/t` — last trade, unix seconds *(verified)* | `close` + `timestamp` (unix) + `last_quote_at` + `is_market_open` *(verified)* | `GLOBAL_QUOTE`; last, prior close and latest trading date, grade EOD *(verified 2026-08-26)* |
| Equity bid/ask | none | none | none; stays NULL |
| FX | **premium only** *(docs)* | free (`EUR/USD` style) *(verified)* | `CURRENCY_EXCHANGE_RATE`; exchange rate plus bid/ask and refresh time *(verified 2026-08-26)* |
| Metals (XAU) | premium | free `XAU/USD` quote *(verified with registered key)* | not registered |
| Indices (^GSPC/SPX) | premium *(docs)* | limited | not registered |
| ETF (SPY) | free, real-time US *(docs)* | free | EOD through `GLOBAL_QUOTE` when explicitly watched |
| Batch | none | **`symbol=A,B,…` — one HTTP call, 1 credit/symbol** *(docs)* | none |
| Symbol search | `/search` + full `/stock/symbol?exchange=US` directory | `symbol_search` — one API credit per request | no typeahead call; attaches to normalized US equity/ETF and FX identities |
| Market open/closed | `/stock/market-status`, free *(docs)* | `is_market_open` on every quote *(verified)* | no session field; equity grade and source date make EOD explicit |
| Error shape | proper `401`/`429` + `{"error": …}` *(verified 401)* | **HTTP 200** + `{"code":429,"status":"error"}` *(verified shape)* | **HTTP 200** `Information`/`Note`/`Error Message`, classified before normalization *(verified throttle)* |

Day ranges, 52-week ranges, volume, order-book depth and open interest stay outside the
normalized contract. The Phase 5 brief needs comparable prices, clocks and provenance;
those adjacent measures have different meanings and provider coverage and do not improve
the required execution demo.

## Official sources

One additional official source supports model valuation. **EIOPA** publishes monthly
risk-free term structures per currency (`www.eiopa.europa.eu`, no key): each country build
reads the release page for the newest `EIOPA_RFR_YYYYMMDD.zip`; the archive download is
cached and shared by the three builds. The `…_Term_Structures.xlsx` inside it has a
column header states the derivation and the parameters — `EUR_…_SWP_LLP_20`,
`US_…_OIS_LLP_30`, `PL_…_GOV_LLP_10`. Verified live 2026-08-24;
the EIOPA archive needs a 60-second client timeout, not the shared 10-second one.

| | NBP | ECB | FRED |
| --- | --- | --- | --- |
| Data | FX fixings: table A (`mid`), gold (PLN per 1 g) | Yield curves **AAA (`G_N_A`) and all-bonds (`G_N_C`)**, tenors `SR_3M…SR_30Y`; EXR FX fixings | `DGS1MO…DGS30` Treasury curve |
| Verified Mon Aug 17 | table `158/A` dated 08-17 and the latest gold fixing | YC as-of 08-14 (Fri, publishes next TARGET day ~noon); EXR 08-17: USD 1.1593, PLN 4.3063 | DGS through 08-13 (1–2 business-day lag) |
| Auth / limits | none; `last/{n}` caps: 67 tables, 255 gold quotations | none; fair use | free instant key; 120 req/min |
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
- The investigation found FRED/OECD Poland observations for a 3M interbank rate and a 10Y
  government yield, but combining those two monthly anchors and interpolating the middle is not
  an index-calibrated projection curve. Phase 6 therefore does not catalog or fetch that set.

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
- **`quote_grade`**: `REALTIME`, `EOD` (Alpha equity daily close), or `REFERENCE`
  (official fixing — NBP, ECB). The grade travels with every quote.
- **Two clocks**: `provider_timestamp` (the provider's own event time, nullable) and
  `received_at` (ingest time). Age is measured on the provider's clock; ingest lag is the
  difference.

Per-provider basis mapping: Finnhub and Twelve Data are last-only; Alpha equity is
last-only while Alpha FX uses returned bid/ask when both are present; NBP table A and ECB
EXR are official mids.

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
timestamp against 3× the closed cadence — STALE means "the feed is broken" in both. An
overnight row classifies internally as CLOSED and renders to the user as `EOD (date)`.
Every tick and snapshot row carries `market_open`,
`stale_after_seconds` and `closed_stale_after_seconds`, so `/quotes` and the UI classify
identically. The market-open flag is Finnhub's exchange-level `/stock/market-status` for
Finnhub rows and Twelve Data's per-symbol `is_market_open` for Twelve Data rows.
MISSING, UNSUPPORTED and STALE block a new trade (enforced at the ticket and the server);
a manual close may use the last stale quote so a position is never trapped by a quiet feed.

Valuation `LIVE` means its required retained inputs match the current inputs: bond checks
discount-curve as-of; IRS checks discount and projection as-of; option checks underlying
quote freshness plus discount-curve as-of. Quote-backed rows show **MKT CLOSED** (distinct
from a closed trade) while the venue is shut. Missing/mismatched curve inputs or a broken/
lagging quote feed give STALE; a flat 10 s wall-clock rule survives only when no market-data
identity is available.

Alpha equity closes have no market-session flag. They remain internally eligible for five
days but every consumer renders the neutral `EOD (YYYY-MM-DD)` label using the provider's
latest trading date; they are never presented as LIVE. Alpha FX uses the returned UTC/GMT
refresh clock and a 26-hour stale limit. Curve sets carry their own catalog age limits
(daily government curves 7 days and EIOPA risk-free curves 75 days); opening
against a set beyond its limit requires the ticket's explicit stale-curve acknowledgement.

Reference rows derive freshness from the publication calendar instead of a cadence: at
store time `stale_after_seconds` = time from the fixing's as-of to the next expected
publication (next business day's window end) + 4 h grace, so a Friday fixing reads current
(the UI renders `CURRENT` for reference-grade LIVE) through the weekend; `market_open`
stays NULL. Source public holidays are not modeled — a holiday Monday reads STALE that
evening until the next real fixing arrives.

### The capability matrix

`shared/providers.py` is the registry: providers, their group, and class-level
capability facts. An asset class absent from a provider's map *is* the UNSUPPORTED state.

| | EQUITY | FX | COMMODITY | curves |
| --- | --- | --- | --- | --- |
| FINNHUB | REALTIME | — | — | — |
| TWELVE_DATA | REALTIME | REALTIME | REALTIME | — |
| ALPHA_VANTAGE | EOD | REALTIME | — | — |
| NBP | — | REFERENCE | REFERENCE (gold) | — |
| ECB | — | REFERENCE | — | ✓ |
| FRED | — | — | — | ✓ |
| EIOPA | — | — | — | ✓ (monthly risk-free per currency) |

Metals re-checked 2026-08-18 with a registered key: Twelve Data serves `XAU/USD` as a
forex-style quote, so XAUUSD is tradeable via Twelve Data. ETFs quote through the equity
endpoints, so SPY is classed `EQUITY`. The matrix
drives the UNSUPPORTED rows in `/quotes`, provider toggles on search results, and the
ticket's N/A rows. The watchlist stores the user's *choice* of providers; capability is
answered from the registry on demand — the two are separate facts. Capability is
class-level today: a ticker one provider lists can still be outside the configured market
entitlement and then remains `NO DATA`.

Ticker alone is not an equity identity across countries. Twelve Data non-US search results
therefore keep the exchange qualifier (`ASB:GPW`) and the UI shows the venue. Its quote API
supports the `symbol:exchange` form, while the normalizer also checks the returned currency
and qualified exchange before persistence. A PLN watchlist entry can never wrap a USD payload.
The concrete 2026-08-25 check found that ASBIS/GPW requires a higher Twelve Data plan; the
board intentionally shows no price rather than falling back to the unqualified NYSE `ASB`.
The quote board presents the stable identity block first: `Symbol`, provider-catalogue `Name`,
`Class`, and exact `Market`. `Market` is a venue (`NASDAQ`, `GPW`, `FSX`) or `OTC`, never a
country guess; an unknown venue is `—`. `Mark`, day move and tick move carry their normalized
quote currency. Identity is repeated on each provider row rather than rendered with HTML
row spans: every row remains readable on its own, unavailable facts render as `—`, and
hover/selection stays rectangular. A second provider still must not silently turn the same
canonical instrument into another name, venue, class or currency.
Symbol, name, class and market are sortable as grouped instruments; provider-level prices are
not used as ambiguous group sort keys.

### Curves

`shared/curves.py` owns the curve-to-provider assignment, currency, functional name and
product-use allow-list. Provider registration must expose exactly the catalog keys assigned
to it, and `build_curve_set` rejects a mismatched provider or currency. A `CurveSet` is
(provider, curve_name, `curve_basis`, currency,
optional `index_tenor`, as-of date) plus ordered `CurvePoint`s and stored source evidence.
FRED/ECB retain decoded responses; EIOPA retains a compact release/series/rates summary
rather than archive bytes. Each point carries `source_series` (the publisher's series id;
NULL marks a publisher-classified extrapolated/non-liquid point) and `source_as_of`.
EIOPA post-LLP rates are published by EIOPA rather than calculated by this desk.
`index_tenor` remains available for a future index-calibrated projection source. `curve_basis`
states **how the numbers were derived**: `GOVERNMENT_BONDS`, `INTEREST_RATE_SWAPS`,
`OVERNIGHT_INDEX`. A set's as-of is the **oldest**
of its sources' dates — a curve is only as current as its stalest anchor, the same rule
the FX resolver applies to cross legs.

**Technical roles follow the basis**, while each `CURVE_CATALOG` entry carries the smaller
product allow-list. The catalog also owns the provider, currency, desk-facing family and
qualifier; `curve_name` is the functional system key. Provider packages map their assigned
keys to series, dataset or workbook coordinates, which remain source-specific provenance.
IRS has one public curve choice per settlement currency: the catalog-approved risk-free set.
Validation copies that name into both discount and projection roles and records
`pricing_approach: SINGLE_CURVE_APPROXIMATION`. Government-bond sets stay bond-only even when
their currency matches. The pricing function still accepts a separate projection curve, but
the public contract does not expose one until a defensible index-calibrated source exists.

The wired catalog (latest stored set per name serves reads; history accumulates one set
per source-day):

| Desk-facing name | System key | Source | Basis | Points | As-of behavior |
| --- | --- | --- | --- | --- | --- |
| EUR · Risk-free | `EUR_RISK_FREE` | EIOPA monthly release, `RFR_spot_no_VA` sheet, Euro column | INTEREST_RATE_SWAPS | 9 (1Y–30Y); liquid to 20Y, longer points NULL-series | monthly, reference date = month end, published ~3rd business day |
| USD · Risk-free | `USD_RISK_FREE` | same release, United States column | OVERNIGHT_INDEX | 9, liquid to 30Y so all sourced | monthly, as above |
| PLN · Risk-free | `PLN_RISK_FREE` | same release, Poland column (EIOPA itself derives Poland from government bonds) | GOVERNMENT_BONDS | 9; liquid to 10Y, 15/20/30Y NULL-series | monthly, as above |
| USD · Government bonds | `USD_GOVERNMENT_BONDS` | FRED, 11 `DGS*` series (1M–30Y), one request each | GOVERNMENT_BONDS | 11, all sourced | daily, 1–2 business-day lag; a series whose newest value is `"."` falls back within a 7-observation lookback |
| EUR · Government bonds · AAA | `EUR_GOVERNMENT_BONDS_AAA` | ECB YC `G_N_A`, one csvdata request | GOVERNMENT_BONDS | ≤11 (3M–30Y), all sourced | daily, publishes ~12:00 CET for the prior TARGET day |
| EUR · Government bonds · all ratings | `EUR_GOVERNMENT_BONDS_ALL` | ECB YC `G_N_C`, one csvdata request | GOVERNMENT_BONDS | ≤11, all sourced | same — its gap to the AAA curve is the credit-quality spread |

Each EIOPA country build reads the release page; under a stable release a provider-wide
cycle therefore makes three page requests plus one archive download. The archive is parsed
with `zipfile` + `ElementTree` (an `.xlsx` is a ZIP of XML — no spreadsheet dependency),
serves all three currencies and is held in the client between builds. Every upstream call
is counted, each build reserves two minute tokens before it starts, and only the first build
normally downloads the held archive. The stored evidence
carries the series code, last liquid point, ultimate forward rate, credit risk adjustment
and selected rates. Licensed benchmarks (Euribor, WIBOR/POLSTR, term SOFR, ICE swap rates) are out
of reach on the free tier, so IRS floating payments are explicitly a single-curve approximation.

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
  (symbol, display name, class, quote currency, exact venue, chosen providers). The ticket's instrument list and
  trade-action's execution gate read it: what isn't watched isn't tradeable, capped by
  `MAX_ACTIVE_SYMBOLS`.
- A successful browser add/remove invalidates the open New Trade catalog and option term
  choices immediately. The ticket refetches both derived endpoints and clears a removed
  selected symbol plus its dependent provider/curve state; polling is the recovery fallback.
- The polled *active set* = watchlist ∪ open-trade symbols ∪ benchmark, reloaded from the
  DB every 15 s.

## Feeds

Each source is readable inside `app/providers/<provider>/`: `client.py` owns transport and
provider-body rules, `normalizer.py` maps quote fields when the source serves quotes,
`curves.py` builds selected rate sets when it serves curves, and `feed.py` wires budgets and
scheduling. Every package exports the same `ProviderRegistration`; the central registry
derives scheduler maps and loops from those registrations. Shared mechanics remain outside
vendor packages: `providers/base.py` for HTTP/error handling, `official_fixing_feed.py` and
`curve_feed.py` for orchestration, `quote_store.py`/`curve_store.py` for persistence, and
`publisher.py` for provider-tagged SSE.

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
- **Session is per symbol** (`is_market_open` on every quote): NVDA classifies CLOSED overnight
  and displays EOD, while EUR/USD on the same provider reads LIVE. FX keeps ticking through the weekend —
  verified Sunday 2026-08-23: `"is_market_open": true`, fresh `last_quote_at`, close
  moving 4.31225 → 4.31182. That is Twelve Data's consolidated retail feed (weekend-active
  venues, indicative pricing); the board reports the provider's claim, and the
  official-rates panel beside it (frozen at Friday's as-of) is the counterweight.
- Errors arrive as HTTP 200 with `{"code": …, "status": "error"}`; `classify_body` maps
  them into the shared state machine.

### Alpha Vantage

- Classes: EQUITY/ETF through `GLOBAL_QUOTE` at grade `EOD`; FX through
  `CURRENCY_EXCHANGE_RATE` at grade `REALTIME`. Equity normalization accepts an unqualified
  US symbol with USD currency and the exact returned symbol. FX normalization checks exact
  from/to currency codes and accepts only UTC/GMT source clocks.
- Every scheduled, add-triggered and manual request shares one persisted daily ledger keyed
  by provider and UTC day (22 safe calls of the published 25) and one provider-wide 15-second
  minimum spacing. Restart seeds due-times from fresh stored observations, restores healthy
  runtime state and does not consume another call.
- US equities refresh once after 16:30 America/New_York on business days. Selected FX rows
  refresh no more than every 12 hours. There is no Alpha typeahead traffic: an existing
  normalized US equity/ETF or FX search identity gains an Alpha toggle locally.
- HTTP-200 `Information` and `Note` bodies become typed rate-limit failures;
  `Error Message` becomes a typed provider-data failure. None can reach normalization or
  storage as a quote.

### NBP and ECB

- Keyless clients (`providers/nbp/client.py` table A + gold; `providers/ecb/client.py` EXR via csvdata — it
  overrides the base `decode_body` hook to parse CSV with the stdlib). Runtimes carry the
  same status machine and cooldowns as quote providers but no rolling minute budget and no daily
  budget (`keyless: true` on `/providers`), only a calls-today counter.
- Calendar windows, not cadences: poll every 5 min inside the source's publication window
  (NBP 11:45–12:20 Warsaw; ECB 15:55–16:45 Frankfurt, business days) until a new as-of
  appears, then hourly confirmation. A failure degrades only that provider's card
  (verified live via DNS blackhole: NBP → ERROR, everything else OK, recovery audited).
- Official-fixing universe = configured defaults (`NBP_FIXING_SYMBOLS`,
  `ECB_FIXING_SYMBOLS`) ∪ settlement currencies of active or closed reportable trades (as `<CCY>PLN` /
  `EUR<CCY>`) while the source publishes them. Full tables are not ingested as rows — each
  snapshot retains the complete raw table response.
- Rows are reference-graded, never tradeable: ordinary `build_quote` with
  `reference_mid`, grade `REFERENCE`, `provider_timestamp` = the as-of date at midnight
  UTC (the source publishes a date, not a time; the UI renders "as of 2026-08-21"). Board
  reads and SSE tag them `reference` (fourth origin flag beside watched/held/benchmark).
  Four independent guards keep them un-tradeable: watchlist validation and symbol search
  offer quote providers only, `/instruments` derives from the watchlist only, and
  trade-action refuses a reference `market_data_provider` with the reason.
- Gold keeps its published unit: symbol `XAUPLN_G`, **PLN per 1 g** (a six-letter
  `XAUPLN` would read as per-troy-ounce, wrong by ×31.1034768); the ounce conversion is a
  documented cross-check, never a stored row.
### FRED and the curve feeds

- `providers/fred/client.py`: key in `api_key`, `file_type=json`; observation values are strings
  with `"."` for missing; a bad/unregistered key answers **HTTP 400** naming `api_key`,
  classified as AUTH_FAILED. Budget: 108/min bucket from the published 120/min.
- Curves are scheduled, not windowed: each builder re-reads on its own interval
  (`CURVE_REFETCH_SECONDS`, 6 h; EIOPA 24 h) and retries 15 minutes
  after a failure. A freshly booted stack builds every set on the first loop tick. The
  publication-window pattern stays with the fixings, where it belongs: a fixing is dated
  the day it is published, so "have we got today's yet?" is answerable, while every curve
  source here publishes with a lag — chasing today's date would poll forever. Manual
  `POST /curves/refresh?curve=` / `?provider=` refetches on demand within the budget.
- ECB's yield curves share the ECB runtime with the EXR fixings and two loops; the runtime
  response exposes separate `feeds.fixings` and `feeds.curves` health snapshots. The former locally entered NBP policy proxy was removed because it was not
  a published term structure.

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
display overlay: the browser multiplies on Valuations, Books and Business Overview —
per-currency subtotals stay primary; converted figures (the headline cards, each book
card, the overview totals) appear only after the user picks a reporting currency (chip
row, remembered per browser); every converted row is labeled with rate, provider and
as-of; an unconvertible currency stays a labeled subtotal with the resolver's reason.
Nothing converted is ever persisted, and no service calls another service's API for it.
The browser's 60 s rate TTL is the only cache — the gateway serves `/fx/rates` from two
small indexed reads.

PnL is never summed across currencies. A book that settles in one currency shows that
currency's amount untouched; a book holding several shows the converted figure labeled
with the reporting currency, or `MIXED` with the resolver's reason when a leg has no
path. The aggregates carry the split that makes this possible: `/books/summary` ships
`subtotals` (unrealized and realized per settlement currency) beside the book's totals,
and the valuation feed's rows carry their own currency.

## Watchlist self-service and discovery

Board rows carry server-truth origin flags (`watched`/`held`/`benchmark`/`reference`);
watched rows get the remove control, held rows a POS tag, the benchmark its own summary
strip. Incapable provider/class pairs are not rendered as board rows — capability shows
where a decision is made (search toggles, ticket N/A). `_board_payload` filters to the
active set on every read; a daily sweep removes stray rows (reference rows validate
against the reference universe).

- `GET /watchlist` — items with chosen providers plus per-class provider capability (two
  separate facts).
- `POST /watchlist {symbol, name?, asset_class, currency, market?, providers?}` — validates canonical
  form, spot classes, `MAX_ACTIVE_SYMBOLS`; omitted `providers` = every capable provider;
  provider search supplies name and exact venue when it knows them, and country-only values
  such as `US` are discarded rather than stored as a venue;
  an incapable named provider is refused with the reason. Adding to an existing symbol is
  a merge, not a 409. Audit row in the same transaction; the add fires one targeted,
  budget-aware refresh per feed actually added, so the first quote lands in seconds.
- `DELETE /watchlist/<symbol>?provider=` — drops one feed or the whole symbol; answers
  `{symbol, removed_providers, remaining_providers, still_polled}`; a `market_remove` SSE
  event names exactly the (provider, symbol) rows every open tab should drop; feeds kept
  alive by a position or the benchmark stay as POS/BMK rows. History rows are untouched.
- `GET /symbols/search?q=` — Finnhub `/search` + Twelve Data `symbol_search` fetched in
  parallel, both through their provider budgets, cached 10 min per query, ranked
  exact-prefix-first and provider-tagged. Normalized US equity/ETF and FX identities attach
  Alpha capability without an Alpha request; retained watchlist identity provides the same
  fallback when one external search budget is unavailable. Results name their quote currency.

The board draws no intraday trend: `market_data_snapshots` holds sparse changes observed
while this application ran, not a market series — connecting them would invent movement
through unobserved time. Selecting a row opens a newest-first tape of its latest 60 stored
changes (one DB read; re-read only on a changed tick; no polling timer, no provider
credits).

### Endpoints

| Route | Serves |
| --- | --- |
| `GET /market-data/snapshot` | current spot/curve maps from PostgreSQL plus `stream_id` and the pre-read `event_id` checkpoint |
| SSE `/market-data/stream` | `market_tick` per successful poll, provider-tagged, with `stream_id`/`event_id` |
| SSE `/market-data/stream/<provider>` | the same contract filtered to one wired provider (quote or reference); unknown/unwired provider is 404 |
| `GET /market-data/quotes` | stored active-set + reference quotes with computed freshness; filterable by `symbol`, `asset_class`, `provider` |
| `GET /market-data/quotes/<provider>/<symbol>` | one active normalized quote; unknown provider or missing row is 404 |
| `GET /market-data/quotes/<provider>/<symbol>/history?limit=&raw=` | latest stored change observations, newest provider timestamp first; limit 1–200; `raw=1` includes each observation's stored raw payload (the provenance drill) |
| `GET /market-data/curves?raw=` | latest stored set per curve: metadata, provenance-carrying points, pricing arrays; `raw=1` adds each set's stored source evidence (decoded response or EIOPA summary) |
| `GET /market-data/curves/<provider>?raw=` | the same filtered to one wired provider; unknown provider is 404 |
| `GET /market-data/curves/<provider>/<curve>/<as-of>?raw=` | one retained curve revision by exact provider, curve name and ISO source date; used to compare a model-priced trade's frozen entry inputs with the current curve; missing revision is 404 |
| `POST /market-data/curves/refresh?curve=&provider=` | targeted curve refetch within the provider budget; without `curve`: every curve the provider (or all providers) builds |
| `GET /fx/rates?to=<CCY>` | one resolution per known currency: rate, path, provider, as-of, or an honest no-path reason |
| `GET /watchlist` · `POST /watchlist` · `DELETE /watchlist/<symbol>?provider=` | the symbol master, self-service — offers quote providers only |
| `GET /symbols/search?q=` | provider-tagged discovery, cached 10 min |
| `GET /providers` | all seven wired registrations with capabilities and runtime: status, budgets/ledgers, market session, active symbols, feed-specific health where relevant, and current poll strategy |
| `GET /providers/<p>/health` | one provider's runtime detail |
| `POST /market-data/refresh?symbol=&provider=` | targeted poll within budget — the watchlist row's `↻` action calls this for exactly that symbol/provider pair and the resulting quote returns over SSE; 404 unknown symbol, 422 unsupported class, 429 budget/pace exhausted, 503 disabled/cooldown. Without `symbol`: the provider's whole set — for NBP/ECB one keyless table refetch republishing every reference row |

The `/market-data/...` forms are canonical on port 8001; short routes remain compatibility
aliases. `/market-data/snapshot` carries the curve sets beside the spot board, and each
curve fetch publishes a `curve_tick` SSE event on the same stream (provider-filterable
like quote ticks) — pricing seeds both from the snapshot and follows both event kinds.
Every quote tick carries the full normalized quote plus `stale_after_seconds`,
`closed_stale_after_seconds`, `market_open` and the origin flags, so any consumer
classifies freshness without asking the server. Each provider HTTP call writes one
`provider_http_response` log line and one minimal `PROVIDER_FETCH_SUCCEEDED`,
`PROVIDER_FETCH_FAILED` or `PROVIDER_FETCH_RATE_LIMITED` audit. Fields are limited to
provider, method, endpoint, status, duration, outcome, optional result count and error type;
response bodies and credentials are excluded.

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

Pricing's spot cache is keyed `(provider, symbol)`; a quote-priced trade is valued exclusively
from its frozen `market_data_provider`, close and final valuation included. The client chooses
provider identity; trade-action prices the fill itself from that provider's board row
(ask/bid/mid by side) and compares the client's `client_seen_price` — past
`TRADE_PRICE_TOLERANCE_PCT` the ticket is refused with the deviation. The trade records
executed price, seen price, provider, provider quote timestamp and, when that exact
observation has a retained snapshot, `entry_snapshot_id` (NULL for an unchanged
confirmation poll — never pointed at an older observation). Pre-binding rows resolve to
`DEFAULT_QUOTE_PROVIDER` and every such resolution logs `trade_provider_defaulted`.

Curve-priced classes (BOND, IRS, EUROPEAN_OPTION) execute **model-priced** through the
same gate: the ticket previews a model value via pricing `POST /price`; trade-action
recomputes the PV itself from the stored curves (`shared/curve_registry` + the asset modules in
`shared/pricing/`) — plus the underlying's board row for options, which passes the
normal freshness gate on its chosen quote provider — and compares the result against
`client_seen_price` (IRS deviation is measured against notional; a zero model value skips
the check). Term validation is shared (`shared/term_schemas.validate_terms`) and enforces
the curve guards in both services identically: settlement currency must have a wired
curve. An IRS must select the approved risk-free curve for its settlement currency; validation
uses that same set for discounting and projection, rejects a distinct submitted projection,
and records the single-curve approximation. Rate terms
(`fixed_rate`, `coupon_rate`) are entered and stored as percent (`4.5`); the same
percent-stored / fraction-wired boundary the curves use is crossed once, inside the relevant
`shared/pricing/<asset>.py` formula. The BOND ticket asks for currency, face amount and cashflow terms;
after a curve is selected, an explicit helper can insert the full-schedule par coupon.
There are no benchmark prefills. The accepted trade records each curve's name, provider
and as-of in its terms
(`discount_curve_as_of`, …); `price_basis` in the audit payload reads `MODEL_PV`;
`market_data_provider` stays NULL for IRS/BOND (there is no quote feed) and is the
underlying's provider for options. Provider/as-of fields are entry provenance, while the
stored names resolve the latest retained sets for later valuation and close. Valuation
payloads stamp `discount_curve` + `curve_as_of`, IRS also stamps `projection_curve` +
`projection_curve_as_of`, and options name `underlying_symbol` while retaining the discount
stamp. `GET /instruments/term-schemas` answers
`{"schemas", "curves"}` — the schemas with resolved choices plus the curve catalog the
pickers and guards read.

Each curve metadata row also exposes `age_days`, `stale_after_days` and `stale`. An open
using any stale selected curve is rejected unless the top-level intent explicitly carries
`stale_curve_acknowledged: true`; the accepted terms freeze the acknowledged curve names.

## Storage

| Table | Role | Keying | Growth |
| --- | --- | --- | --- |
| `market_data_spot_prices` | latest quote board — what the UI, ticket and pricing read | unique (provider, symbol), upserted | bounded: one row per pair |
| `market_data_snapshots` | quote history, one row per *changed* quote, with `raw_payload` | append; indexed (provider, symbol, received_at) | ~10k rows/day worst case; swept daily past `SNAPSHOT_RETENTION_DAYS` |
| `market_data_curves` + `market_data_curve_points` | curve sets (basis, stored source evidence) / per-point provenance | unique (provider, curve_name, as_of_date); same-date revisions replace points in place | ≤ one retained set per source date; not swept — years fit in megabytes |
| `watchlist_items` | the symbol master | symbol (primary key) | user-bounded (cap 25) |
| `provider_request_ledgers` | restart-safe daily request/credit spend | provider + UTC usage date | one small row per metered provider-day |

Provenance chain: quote-priced trades carry `market_data_provider`; all trades carry
`entry_price_timestamp`, `client_seen_price`, optional `entry_snapshot_id`, and matching
close fields. Curve-priced terms carry curve provider/as-of; valuations stamp the quote or
discount-curve provider plus timestamp, including the terminal row. The snapshot FKs are strict (no cascade):
the retention sweep skips rows referenced by trades, so execution provenance outlives the
window. The board carries no raw payload — history owns raw. Reference feeds add one board
row per configured pair plus gold, and change-only history means a handful of snapshot
rows per source per day, each carrying the full raw table. Curve-priced trades freeze
their curve provenance in `metadata` — the drill from a trade runs trade → frozen curve
name + as-of → retained `market_data_curves` row → stored source evidence. It is traceable,
but not immutable across a provider revision for the same as-of date.

Quote persistence follows the economic-change rule: a changed price writes the snapshot and
`QUOTE_WRITTEN`; an unchanged confirmation updates the current row clocks only.
