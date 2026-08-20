# Implementation roadmap — real-data trading system

This roadmap records capability boundaries, dependencies, technical decisions and acceptance
checks for the real-data trading system. It is a forward-looking companion to the current-state
guides under `docs/implementation/`; implemented behavior is authoritative there.

The migration starts from `trading-microservices`, removes synthetic/static market flows and
rebuilds market data around real providers. Provider facts come from live probes performed on
2026-08-17 or from provider documentation and are marked accordingly. Revalidate documented
limits when registering production keys.

The core sequence is budgeted at roughly 14–15 focused engineering days. Hosting and the
technical load dashboard are a separate 3–4 day capability group. Automated strategy execution
is deliberately deferred until the market-data, execution and operational foundations are
complete.

---

## 1. The premise: fork, clear, rename

**Mechanics.** GitHub cannot fork a repo into the same account. The correct move:
`git clone --bare` the current repo → push to a new repository (full history preserved) → tag the
old repo's final state (`pre-fork-final`) → add a one-paragraph pointer to its README
("continued in <new-repo>") → **archive** the old repo. The archived repository remains the
runnable synthetic baseline; the new repository contains only the real-data architecture.

**Naming — `trading-desk`.** It names what the system actually is
(a mini front-to-back desk: market data → ticket → blotter → books → risk) and reads
professional on a portfolio.

**What the fork buys.** The archived repository preserves the synthetic baseline without a
runtime compatibility flag. The real-data repository therefore needs no `SIMULATED` provider,
random flow, or generator-specific branch threaded through the provider abstraction.

---

## 2. What the API research established (live probes, 2026-08-17)

### Group A — quote providers

| | Finnhub | Twelve Data | Alpha Vantage |
| --- | --- | --- | --- |
| Free budget | **60 req/min** | 8 credits/min, **800/day** (the real constraint) | **25 req/day** |
| Equity quote | `c/d/dp/h/l/o/pc/t` — last trade, unix seconds *(verified)* | `close` + `timestamp` (unix) + `last_quote_at` + `is_market_open` *(verified)* | `GLOBAL_QUOTE`: price/OHLC/volume, **date-only timestamp** *(verified)* |
| Equity bid/ask | none | none | none |
| FX | **premium only** *(docs)* | free (`EUR/USD` style) *(verified)* | free — `CURRENCY_EXCHANGE_RATE` has **real bid/ask + full datetime** *(verified)* |
| Metals (XAU) | premium | sandbox-blocked — verify with real key | sandbox-blocked — verify with real key |
| Indices (^GSPC/SPX) | premium *(docs)* | limited | premium |
| ETF (SPY) | free, real-time US *(docs)* | free | free (EOD grade) |
| Batch | none | **`symbol=A,B,…` — one HTTP call, 1 credit/symbol** *(documentation; verify with a real key)* | none (bulk = premium) |
| Symbol search | `/search` + full `/stock/symbol?exchange=US` directory, free | `symbol_search` — works **without a key** *(verified)* | `SYMBOL_SEARCH`, free *(verified)* |
| Market open/closed | `/stock/market-status`, free *(docs)* | `is_market_open` on every quote *(verified)* | static hours in search metadata |
| Error shape | proper `401`/`429` + `{"error": …}` *(verified 401)* | **HTTP 200** + `{"code":429,"status":"error"}` *(verified shape)* | **HTTP 200** + `"Information"`/`"Note"` key *(verified)* |

### Group B — official sources

| | NBP | ECB | FRED |
| --- | --- | --- | --- |
| Data | FX fixings: table A (`mid`), **table C (`bid`/`ask`)**, gold (PLN per 1 g) | Yield curves **AAA (`G_N_A`) and all-bonds (`G_N_C`)**, tenors `SR_3M…SR_30Y`; EXR FX fixings | `DGS1MO…DGS30` Treasury curve; SOFR/DFF; **OECD Poland series** |
| Verified Mon Aug 17 | table `158/A` dated 08-17; C: bid 3.6804 / ask 3.7548; 157/C was Friday — clean business-day sequence | YC as-of 08-14 (Fri, publishes next TARGET day ~noon); EXR 08-17: USD 1.1593, PLN 4.3063 | DGS through 08-13 (1–2 business-day lag); SOFR through 08-14; **Poland monthly through 2026-06** |
| Auth / limits | none; 93-day range cap | none; fair use | free instant key; 120 req/min |
| Format note | plain JSON | **use `format=csvdata`** — SDMX-JSON nests values ~5 levels deep; CSV is stdlib-parseable | JSON; values are *strings*, missing = `"."` |

### The ten consequences that shape v2

1. **No free Group-A source gives equity bid/ask.** The PDF's bid/ask-mapping decision is the
   *main case*, not an edge case → D11.
2. **Alpha Vantage equities are EOD** (date-only timestamp). Pretending otherwise would be a
   freshness lie → the `quote_grade` concept (REALTIME / EOD / REFERENCE), D3.
3. **Twelve Data's real constraint is the daily cap** (800), not the per-minute one → budget
   governor spreads credits across the day, D7.
4. **Finnhub has no free FX** → per-provider capability differs by asset class → the fourth
   freshness state **UNSUPPORTED** (a capability fact, distinct from MISSING data), D3.
5. **The PLN curve is viable on real data**: FRED's OECD Poland series are alive —
   `IR3TIB01PLM156N` (3M interbank) and `IRLTLT01PLM156N` (10Y gov bond), monthly, ~2-month
   lag → D6.
6. **ECB serves two genuine EUR curves** (verified keys) → real projection-vs-discount choice;
   and ECB×NBP FX cross-check agreed to <0.3% today → the disagreement-in-bps idea works on
   official data too.
7. **Errors hide in 200 bodies** (Alpha Vantage `"Information"`, Twelve Data `code` field) →
   the client's error classifier must read bodies, not just status codes.
8. **Benchmark: SPY on Finnhub.** Indices are premium everywhere; SPY is a free real-time S&P
   500 proxy (returns-identical for alpha/beta) → D14.
9. **Symbol search is free on all three** (Twelve Data's needs no key at all) → the
   watchlist/discovery feature is cheap → D4.
10. **NBP has no interest-rate endpoint** (404 verified) → the PLN-curve investigation
    narrative stands as the domain-analysis centerpiece.

---

## 3. The clearing inventory (what Phase 0 deletes)

From the survey — everything that constitutes "static previously defined flows":

- **trade-generation-service, whole service**: `generator.py` (random open/close engine),
  its four HTTP clients, `/generate-once|start|stop|status|config` endpoints, seeding in
  `main.py`, the compose block (port 8007), env knobs `TRADE_GENERATION_INTERVAL_MS` /
  `TARGET_OPEN_TRADES` / `TARGET_NOTIONAL` (referenced nowhere else), monitoring target
  (auto-drops when its env URL is unset).
- **Frontend Generator surface**: `views/Generator/`, `components/generator/IntentFeed.jsx`,
  `domain/generator.js`, `config/generator.js`, its route, endpoints, vite proxy entry,
  `serviceStatus.js` display-order entry, two SCSS files.
- **market-data-service simulator**: `generator.py` (random-walk threads), hardcoded seeds in
  `persistence.py:19-49` (ACME/XAUUSD/ES_FUT/EURUSD/MARKET_INDEX + `USD_GOV` anchors),
  `MARKET_INDEX` synthetic basket.
- **Scenarios**: `full-flow.http` (generator-driven); others get rewritten in Phase 7.
- **Catalog**: `INSTRUMENT_CATALOG` is *not* generator-only — trade-action validation, term
  schemas and the ticket depend on it — so it is **replaced** by the symbol master (D4) in
  Phase 1, not deleted in Phase 0.

Compose lands at 8 services: postgres, db-migrations, market-data, pricing, monitoring, books,
trade-action, blotter (+ frontend). HW6's strategy runner will be a new, purpose-built service.

---

## 4. Decisions v2

Numbering continues from v1; each is chose / rejected / why. Status: **revised**, **new**, or
unchanged.

**D1 (revised) — Fork, don't flag.** New repo per §1; delete simulator + random flows entirely.
*Rejected:* v1's `SIMULATED`-provider-behind-a-flag — the fork made that compromise pointless,
and carrying synthetic machinery through the provider abstraction taxes a clean project. If
offline operation is ever needed, the honest future option is a *replay provider* that replays
persisted real history (deterministic, no randomness) — noted, not scoped.

**D2 (sharpened) — Provider frozen on the trade, with an exact provenance pointer.** `trades`
gains `market_data_provider`, `entry_price_timestamp`, **`entry_snapshot_id` (FK to the
`market_data_snapshots` row used at execution — one join from any trade to the provider's raw
payload)**, `client_seen_price`, `created_by_service`; `trade_price` becomes the *executed*
price (D12). `valuations` gains `market_data_provider`, `market_data_timestamp`. Curve choices
stay in frozen JSONB terms — they are economics, not query dimensions.

**D3 (extended) — Freshness: two clocks, four states, graded.** Two timestamps per quote
(`provider_timestamp`, `received_at`). States per (provider, symbol): **LIVE / STALE / MISSING /
UNSUPPORTED** — UNSUPPORTED is a static capability fact (e.g. FX on Finnhub), never confused
with missing data. Thresholds = 2–3× the *scheduled* cadence per provider × asset class; each
provider column carries a `quote_grade` (REALTIME / EOD / REFERENCE) so Alpha Vantage's EOD
equities read honestly as "EOD (Aug 15)" instead of fake-LIVE. Policy: **MISSING and UNSUPPORTED
block the trade; STALE warns and requires an explicit acknowledgement recorded in the audit
trail.** Market open/closed (free Finnhub endpoint + Twelve Data's flag) shows a CLOSED badge so
weekend staleness reads as expected, not broken.

**D4 (revised) — Dynamic active set replaces the fixed catalog.** The polled universe is
**watchlist ∪ open-trade symbols ∪ benchmark**, capped by `MAX_ACTIVE_SYMBOLS` (decided: 25 to
start; adding beyond the cap blocks with an explanation) — the cap *is* the honest rate-limit
contract, surfaced in the UI. `shared/symbols.py` keeps
per-provider symbol conventions plus a **capability matrix** (which providers quote which
symbol/class — computed once at watchlist-add, cached). Discovery = a search box backed by the
providers' free search endpoints, provider-tagged and cached. `INSTRUMENT_CATALOG` consumers
(trade-action validation, term schemas, ticket) migrate to the symbol master. *Rejected:*
polling "the full market" — free budgets make that a lie; the watchlist makes scope a user
decision.

**D5 (confirmed) — Three quote tables, three jobs, bounded growth.**
`market_data_spot_prices` = **latest board**: one row per (provider, symbol), upserted — the
thing the UI, ticket and pricing read. `market_data_snapshots` = **append history**: one row per
*changed* quote with `raw_payload` (change-only insert means closed markets write ~nothing),
swept by a retention job (`SNAPSHOT_RETENTION_DAYS`, default 30). `market_data_curves` (+ new
`market_data_curve_points`) = curve sets upserted by (provider, curve, as_of_date) — ≤ one set
per source per day *by construction*. Growth math at 25 active symbols: Finnhub ≤ ~10k rows/day
worst case, Twelve Data ≤ 800, Alpha Vantage ≤ 25, curves ≤ ~40 points/day → trivial for
Postgres, flat under retention. This answers "fresh enough without overflowing the DB" with
numbers.

**D6 (upgraded) — Curve catalog, now fully verified.**
- `USD_TREASURY` — 11 FRED DGS series, 1–2 business-day lag; par-treated-as-zero documented.
- `EUR_GOV_AAA` / `EUR_GOV_ALL` — ECB `G_N_A` / `G_N_C` (both keys verified), `SR_3M…SR_30Y`,
  `csvdata` format; two real EUR curves make projection-vs-discount selection genuine.
- `PLN_REF` — **composite from live FRED/OECD series**: 3M interbank + 10Y gov bond, monthly,
  ~2-month lag, interpolated between two real anchors, explicitly labeled; the investigation
  write-up (NBP has no rates API — 404 verified; WIBOR licensed; what the lag costs) remains
  the domain-analysis centerpiece.
- `PLN_NBP_BASE` — a second PLN curve: flat at the NBP reference rate (config-sourced — NBP
  publishes the rate but not via the API — clearly labeled a proxy). Two PLN curves make
  **projection-vs-discount selection demonstrable on the PLN swap itself**.
- **The tenor dimension, honestly** (audit fix — his verbatim example was "wibor trzymiesięczny,
  wibor sześciomiesięczny… na swapie na złotówce" [00:05:45]): curve metadata gains an
  `index_tenor` label, IRS terms gain `floating_rate_index_tenor`, and validation matches the
  projection curve's declared tenor to the leg — so the *mechanism* he described exists in
  schema, pickers, and rules. What free data cannot supply is the tenor-differentiated *curves*
  themselves (WIBOR 3M/6M are licensed; EMMI Euribor likewise) — the domain write-up states
  this trade-off explicitly instead of silently narrowing his ask.
- NBP tables A/C + gold and ECB EXR stored as reference quotes (`REFERENCE` grade, daily
  thresholds). NBP gold is PLN per **gram**; XAU/USD is per troy ounce — the documented
  conversion (×31.1034768) is a nice cross-check detail.

**D7 (concretized) — Scheduler = per-provider budget governor.** Token bucket at a configurable
90% of the
published budget; priority tiers (open-trade symbols + benchmark first, rest of watchlist
second); provider cycles offset in time so the board refreshes rolling, not in synchronized
bursts. Per provider: **Finnhub** round-robin — tier-1 ~15 s, tier-2 ~60 s, decaying to ~5 min
when the market is closed; **Twelve Data** — one batch call (≤8 symbols) per ~15 min, sized by
the remaining *daily* ledger; **Alpha Vantage** — fixed daily slots (equities once after US
close — they're EOD anyway; FX bid/ask anchor 2×/day) plus a 5-call reserve for manual refresh;
**Group B** — calendar windows in each source's timezone (NBP ~08:15/12:15 CET, ECB YC ~12:00
CET, ECB EXR ~16:00 CET, FRED ~16:15 ET) polled until a new as-of appears, then asleep till the
next window; OECD Poland checked weekly. `429`/limit bodies classify as `RATE_LIMITED` (own
state + audit + cooldown), never as generic errors; `Retry-After` respected. Opening a ticket
fires a targeted `POST /market-data/refresh?symbol=` within budget (Finnhub always, Twelve Data
if headroom, Alpha Vantage only via an explicit button showing remaining budget).
**Budget isolation is a rule, not an emergent property:** each
provider keeps its own ledger, and within a provider each asset-class feed keeps its own
cadence — a scarce feed (Alpha Vantage equities at 25/day) never drags a rich one (Finnhub
equities at 60/min) down to a defensive common denominator. Poor-availability feeds simply
refresh less, and their D3 freshness thresholds follow their *actual* cadence, so the UI reads
honest instead of falsely STALE. `RATE_LIMITED` cooldowns are reactive and scoped to the
provider key that tripped them — never global, never preemptive.

**D8 (unchanged) — Decimal policy.** Cashflow/discount math in `Decimal`; Black–Scholes stays
float behind one documented boundary; the cache parses wire strings to Decimal at ingest —
which also kills the scenario-shock no-op bug found in the survey.

**D9 (superseded by D1) — trade-generation-service is removed in Phase 0.** HW6's strategies
get a fresh, purpose-named service later. *Rejected:* keeping an idle shell — dead weight in a
clean project; the old repo preserves the pattern.

**D10 (unchanged) — Multi-currency PnL, minimal and honest.** Per-currency subtotals +
one converted total using the latest official reference rate (NBP/ECB), labeled with its as-of.

**D11 (new) — Price basis & bid/ask mapping (the README-documented policy).** Store `bid`,
`ask`, `last` exactly as the provider gave them — absent fields stay NULL, **never synthesize a
spread**. Derive `mid` := (bid+ask)/2 when both exist, else `last`. Tag every quote with
`price_basis` ∈ {BID_ASK, LAST, REFERENCE_MID}. **Execution is side-aware: BUY fills at `ask`,
SELL at `bid`, falling back to `mid` when the side price is absent; valuation and display
headline always use `mid`.** Per-provider mapping table goes in the README (Finnhub last-only;
Twelve Data last-only; Alpha Vantage equity last-only/EOD, FX true bid/ask; NBP A = official
mid, C = official bid/ask; ECB EXR = official mid). *Rejected:* fabricating bid/ask via an
assumed spread (invents data — the PDF explicitly permits empty fields); trading at mid when a
real ask exists (throws away the one place spread realism is available).

**D12 (new) — Execution is server-priced; the client's price is a check, not the price.**
Today trade-action trusts `trade_price` from the caller (its only check: parseable and > 0).
v2: the ticket sends `provider` + `client_seen_price` + the board row's snapshot ref;
trade-action **re-reads that provider's latest board row**, enforces the D3 gate
(MISSING/UNSUPPORTED reject; STALE requires the ack flag), executes side-aware per D11 at the
*server's* price, rejects with `PRICE_MOVED` if it deviates from the seen price by more than a
tolerance (env, default 1%), and records both prices — the difference is the trade's recorded
slippage. Close runs the same path, side-inverted, on the frozen provider. *Rejected:* trusting
the client price (unauditable with real data); pure server pricing with no seen-price check
(silent fills far from what the user was shown).

**D13 (new) — Comparison is display-wide; valuation is provider-narrow.** The board and ticket
may show cross-provider aggregates — freshest-quote badge, spread between sources in bps —
always labeled as display. Money math never mixes: valuations and PnL read exclusively the
trade's frozen provider; the benchmark series reads its configured provider. (This is the
answer to "smart order for freshest valuations": *display* aggregates freely; *valuation*
follows the binding.)

**D14 (new) — Benchmark = SPY on Finnhub.** `BENCHMARK_SYMBOL=SPY`,
`BENCHMARK_PROVIDER=FINNHUB`; SPY always sits in the active set's first tier. S&P 500 answer:
yes — via the ETF proxy, because indices are premium on all three providers and SPY's *returns*
(all alpha/beta needs) track the index. The estimator itself survives unchanged, as
`decisions.md` bet it would.

**D15 (new) — The curve chart stays hand-rolled SVG.** Build a small `CurveChart` (tenor axis,
per-curve series, as-of + provider caption) — `package.json` has zero chart dependencies;
consistency beats a library for one chart. *Rejected:* adding recharts/d3 for a single plot.

**D16 (decided) — Naming & fork mechanics** as §1: bare-clone push, archive + pointer; the new
repository is **`trading-desk`**.

**D23 (new) — Currency conversion has one owner.** A single FX resolver (`shared/fx.py`):
`convert(amount, from_ccy, to_ccy)` returns the converted amount **with full provenance** —
rate, path, provider, as-of. Precedence: identity → direct official rate or its inverse →
single cross via EUR (ECB EXR quotes ~30 currencies against EUR, so one hop covers nearly
everything) → cross via PLN (NBP tables) as the fallback; a conversion path never mixes
sources. `Decimal` throughout; rates come from the reference-quote board at daily cadence.
Consumers: books per-currency totals (D10), any converted figure in the UI — and every one of
them displays the as-of + path label ("USD→PLN via EUR, ECB EXR 2026-08-15"). *Rejected:*
ad-hoc conversion at call sites (drift and silent source-mixing); converting through live
tradable quotes (reference fixings are the honest daily standard for reporting — and Finnhub
has no free FX anyway).

**D24 (new) — Config is explained or it doesn't exist; code explains itself.** Every tunable is
an env var whose line in `.env.example` carries a one-line rationale saying *why this value for
this provider* — e.g. `ALPHA_VANTAGE_DAILY_BUDGET=20` (25/day free tier minus a 5-call
manual-refresh reserve), `FINNHUB_TIER1_POLL_SECONDS=15` (60/min free tier below its safe utilization
across a 25-symbol set), `TRADE_PRICE_TOLERANCE_PCT=1.0` (fills rejected beyond 1% of the seen
price), `IDLE_PAUSE_MINUTES=12` (inside the 10–15 min window; above Railway's 10-min sleep
threshold). `docs/configuration.md` mirrors the full table with per-profile defaults. The
counterpart rules: **code carries no comments** — it is written to be self-explanatory, with
all rationale in `docs/`; the **README shrinks to only what a stranger needs** to run and test
(the PDF's required sections, kept lean, linking into `docs/` for approaches and decisions);
and **config controls in the UI live on technical views only** (SystemOverview/monitoring),
never on business screens. The six provider clients follow **one enforced module shape** —
same base class, same
client/normalizer pairing and same method names — so learning one provider path transfers to
the others.

**D25 — Verification = scenario flows + scenario load tests;
no unit-test suite.** The house convention stays: `scenarios/*.http` flows verify behavior
end-to-end through the real system (rewritten for the provider world in Phase 7). The
load layer uses **scripted scenarios** — small stdlib scripts (urllib + threads, no frameworks)
injecting load at
the system's internal seams, each with a measured result recorded in `performance.md`:

- `load_ticket_storm` — N concurrent clients submitting open/close intents: queue depth,
  latency, idempotency under duplicate `client_request_id`s.
- `load_sse_fanout` — K concurrent stream clients: fan-out cost and the bounded queues'
  drop behavior.
- `load_active_board` — the 25-symbol watchlist at full budget cadence for hours: DB growth
  vs the D20 ceilings, RAM/CPU per container.
- `load_valuation_soak` — many open trades on live cadences: pricing CPU and the valuation
  write throttle provably doing its job.

Provider APIs are never load-tested (their rate limits are contractual) — load enters behind
the gateway. Every run records `docker stats` before/during/after. A unit-test suite remains
out of scope because the scenario harness
exercises the same logic through the real system instead.

---

## 5. Target architecture

### market-data-service layout

```
app/
  api.py           # /providers, /providers/<p>/health, /market-data/{snapshot,quotes,stream,refresh},
                   # /curves(/…,/refresh), /symbols/search — plus SSE
  clients/base.py  # urllib: timeout, retries, key injection, body-aware error classification
  clients/{finnhub,twelve_data,alpha_vantage,nbp,ecb,fred}.py
  normalizer.py    # raw payload -> NormalizedQuote / CurvePoints (basis, grade, two clocks)
  scheduler.py     # per-provider threads, priority tiers, calendar windows, stagger offsets
  budget.py        # token buckets + daily ledgers (surfaced on /providers)
  persistence.py   # board upsert, change-only history append, curve upsert, retention sweep
  publisher.py     # provider-tagged SSE fan-out (kept from today)
```

### Data model (fresh DB via the existing migration chain + one new migration)

| Table | Role | Keying | Growth |
| --- | --- | --- | --- |
| `market_data_spot_prices` | latest quote board | unique (provider, symbol), upsert | bounded: one row per pair |
| `market_data_snapshots` | quote history + raw payloads | append, change-only | ~10k rows/day worst case; retention-swept |
| `market_data_curves` / `market_data_curve_points` | assembled curves / point provenance | upsert by (provider, curve, as_of) | ≤1 set/source/day |
| `watchlist_items` | the client's active universe | (watchlist implied single, symbol) | user-bounded |
| `trades` | + provider, entry ts, snapshot FK, seen price, executed price | — | as today |
| `valuations` | + provider, market_data_timestamp | — | slower than today (real cadences) |

### Freshness spec (excerpt — full table lands in README)

| Provider × class | Grade | LIVE while | Notes |
| --- | --- | --- | --- |
| Finnhub equity/ETF | REALTIME | ≤ ~45 s (tier-1) / ≤ 3 min (tier-2) | CLOSED badge outside RTH |
| Twelve Data equity/FX | REALTIME | ≤ ~30 min | daily-ledger cadence |
| Alpha Vantage equity | **EOD** | latest_trading_day == last US close | date-only timestamp |
| Alpha Vantage FX | REALTIME | ≤ ~12 h | true bid/ask, 2 fetches/day |
| NBP / ECB EXR | REFERENCE | as-of == last business day | fixings, not feeds |
| FRED curves | REFERENCE | as-of ≥ 2 business days back | H.15 lag observed |
| PLN composite | REFERENCE | as-of within ~75 days | monthly series, labeled |

---

## 6. Phases

Each phase ends with an executable acceptance check and updates the relevant feature guide.

### Phase 0 — Fork & deep clean *(~1.5–2 days)*
This phase is intentionally **deep** — the fork must contain no rubbish, and simplification
by extraction is in scope, not just deletion.

- New repo **`trading-desk`** (D16); old repo tagged, pointed, archived. Delete the §3
  inventory; compose lands at 8 services.
- **Dead-code sweep** beyond the inventory: everything the clearing orphans (frontend
  `MARKET_INDEX`/basket paths and `MarketIndexCard` wiring, generator-only domain/config
  modules, unused exports, orphaned SCSS), repo hygiene (`tmp/` and `logs/` untracked,
  `.dockerignore` added).
- **Extract what every service repeats**: a shared service bootstrap
  (`shared/service_runtime.py` — threaded WSGI boot, IPv6-ready server class, health route,
  logging setup) so eight `main.py` files become declarations instead of copies; config access
  unified through one module. (This also pre-pays Phase 8.1's portability work.)
- **Slim images**: `python:slim` multi-stage, 1.69 GB → ~200 MB — faster local builds now,
  Railway-ready later.
- `.env.example` rewritten in the D24 format — every knob with its one-line why; register all
  four API keys.
- **README reset to the minimal runbook** (D24); approach/decision prose lives under `docs/`.
- Verify metals capability on Twelve Data / Alpha Vantage with the real keys (decides
  XAUUSD's fate).
- **Verify the preserved baseline before archiving**: fresh-clone the old repository at its
  final tag, run `docker compose up --build`, and exercise its primary workflow.

**Acceptance check:** clean boot of `trading-desk` — no synthetic data anywhere, empty-but-honest UI,
health green, and a repository a developer can read without tripping over leftovers.

### Phase 1 — Contracts & schema *(~1 day)*
`shared/`: normalized-quote + curve-point contracts, provider registry + capability matrix,
`freshness.py` (four states, grades), `symbols.py` (conventions; catalog consumers migrated).
One hand-written migration: board uniqueness + quote columns (bid/ask/last/mid/basis/two
clocks), history reshape, curve tables, trades/valuations columns (D2), `watchlist_items`.
Start `docs/market-data.md` seeded with §2's fact sheets — the domain analysis is pre-written.
**Exit:** migration up/down clean on a fresh DB.

### Phase 2 — Finnhub vertical slice *(~2 days)*
`clients/base.py` (body-aware error classification), Finnhub client + normalizer, scheduler v1
(active set, token bucket, market-status awareness), board upsert + change-only history +
provider-tagged SSE, endpoints (`/providers`, health, quotes, refresh), pricing cache keyed
(provider, symbol), UI board shows provider + age from `provider_timestamp`.
**Acceptance check:** live AAPL on screen with honest age; a manual trade valued off Finnhub through
the (provider, symbol) cache.

### Phase 3 — Watchlist, second provider and honest board

Phase 3 is split by dependency. **3a** completes the core two-provider workflow end to end;
**3b** adds provider breadth and pacing refinements after that path is stable.

**Phase 3a — core multi-provider workflow:**
1. **CLOSED freshness state** *(ruling; refined 2026-08-19: a first-class state, not a
   display remap)*: fifth state in `shared/freshness.py`, so `/quotes` and the UI classify
   identically and rows stay self-classifying (ticks and `/snapshot` rows gain the
   market-open flag). Classification: market open → LIVE/STALE by `provider_timestamp` age
   vs 3× open cadence (unchanged); market closed → **CLOSED** while confirmation polls keep
   arriving (`received_at` age ≤ 3× closed cadence, 900 s), STALE once they stop. STALE
   thereby means "the feed should be updating and is not" in both regimes; CLOSED renders
   neutral; the Age column keeps counting from the provider clock.
2. **Watchlist self-service**: symbol search endpoint (Finnhub `/search`) + watchlist CRUD +
   board rework — the board *is* the watchlist (one row per provider × symbol), search box,
   add/remove, UNSUPPORTED cells from the capability matrix.
3. **Twelve Data wired as the second provider**: client + normalizer (quote; `EUR/USD` /
   `XAU/USD` notation is the client's concern) + feed with the daily-ledger governor —
   spread the 800/day across the day alongside the per-minute bucket; batch endpoint if it
   proves as probed, else per-symbol.
4. **Provider ops card on System Overview** *(ruling)*: per-provider status, budget gauges,
   spend today, market session — reads `/providers`.
5. **Intraday chart deliberately omitted**: `market_data_snapshots` is sparse application
   observation history, not a complete market series. Finnhub candles require Premium
   access and Twelve Data history alone would make provider rows asymmetric, so the board
   shows a structured quote summary and a discrete selected-row observation tape instead of
   drawing an incomplete trend.

Validation fixtures: NVDA searched + added live; EURUSD and XAUUSD on Twelve Data with
UNSUPPORTED under Finnhub — board display only, FX/commodity *trade valuation* stays out of
scope until its branch is rewired. The validation workflow lives in
`docs/validation-runbook.md`.
(what to click, what to say, how to reset).
**Acceptance check:** search "NVDA", add it, watch two providers populate at their honest
cadences; EURUSD/XAUUSD quote on Twelve Data while Finnhub's cells read UNSUPPORTED; with
the US market closed the board reads CLOSED, not STALE; the System Overview card shows both
budgets moving; kill the Twelve Data key → its rows degrade visibly, Finnhub unaffected.

**Phase 3b — breadth completion *(~2026-08-27, first after the pause)*:**
Alpha Vantage wired (EOD equities with grade chips telling the truth on the board; FX with
real bid/ask; `"Information"`/`"Note"` 200-body error classification; the 25/day governor);
governor stagger + remaining-budget pacing polish; `MAX_ACTIVE_SYMBOLS` cap enforcement
(D4); per-symbol capability matrix cached on the watchlist row (D4).
**Acceptance check:** Alpha Vantage's column reads "EOD (Tue)" honestly next to two live columns,
and its 25/day budget visibly paces itself on the ops card.

### Phase 4 — Trading flow refactor *(~2 days)*
Ticket v2: per-provider comparison row (value, grade, age, state pill, disagreement in bps),
provider radio, STALE ack flow, targeted-refresh button. trade-action: D12 server-side
execution (freshness gate, side-aware price, tolerance, snapshot FK freeze, slippage record);
close path identical. Valuations stamped with provider; blotter/trades views gain the provider
column.
**Acceptance check:** execute the provider-selection ticket scenario end-to-end; the trade's PnL moves only with
its frozen provider.

### Phase 5 — Curves & multi-curve pricing *(~2.5 days)*
NBP/ECB/FRED clients; calendar-window scheduling; curve points → assembled curves →
`/curves` endpoints + curve SSE; **CurveChart** (D15) + curve inspector (per-point provenance);
pricing curve registry; `TERM_SCHEMAS` gains `settlement_currency` / `discount_curve` /
`projection_curve` / `floating_rate_index_tenor` → ticket pickers appear server-driven;
**currency guard** (curve currency must equal settlement currency) and **tenor guard**
(projection curve's declared `index_tenor` must match the leg) — both reject with readable
reasons; both PLN curves (composite + NBP-base proxy) + the write-up; per-currency PnL
subtotals (D10); a curve-selection scenario flow lands in `scenarios/` (D25).
**Acceptance check:** a PLN swap prices with a *chosen*
projection curve (two PLN curves to choose from) and is rejected when pointed at
`USD_TREASURY`; EUR AAA vs ALL selectable; the tenor mechanism demonstrated in schema and
validation, with the write-up stating why free data can't supply WIBOR 3M/6M curves
themselves.

### Phase 6 — Provenance & polish *(~1.5 days)*
Trade detail provenance block (provider → executed vs seen price → snapshot FK → raw payload →
audit story link); valuation-blocked honest UI state + audit; alpha/beta flipped to
SPY@Finnhub; board best-quote badge + bps disagreement (D13); audit-event completeness pass
against the PDF's list. *(Shock absorber: everything here degrades gracefully if time runs
out.)*
**Acceptance check:** click any trade and trace the price, provider, timestamp and original
provider payload without leaving the screen.

### Phase 7 — Hardening & documentation *(~1.5 days)*
D8 Decimal conversion + telescoping re-verification; idempotency (duplicate poll → zero
duplicate rows) + restart warm-start; **the D25 scenario load tests** (ticket storm, SSE
fan-out, active-board soak, valuation soak) with `docker stats` CPU/RSS per container
recorded into `performance.md`; README covers the required operational and domain sections
(per-provider endpoint docs from §2, D11 price-basis policy, D3 STALE rationale argued from
market hours, keys how-to, run + test); scenarios refreshed (delete `full-flow.http`, add
provider/watchlist/ticket flows); decisions register updated (D1–D25); operational analysis
scans the existing log corpus for warnings/errors evidencing write contention and records the
result; the numerical analysis documents the **Black–Scholes Decimal boundary**: why
`erf`/`log`/`sqrt` stay float, error magnitude versus the Decimal
quantization at the boundary, and the fact that every money leg remains Decimal.

---

## 7. UI plan — reuse map

| View | Keeps | Changes |
| --- | --- | --- |
| MarketData | two-table layout, DataTable/MarketCell machinery | instruments table becomes the **watchlist board**: search+add, per-provider expandable rows (or provider columns), mid headline + basis tag, grade/age chips, CLOSED badge, UNSUPPORTED cells; curve section gains **CurveChart** + inspector with as-of + provider |
| Trades / NewTradePanel | form flow, TERM_SCHEMAS-driven fields, validation UX | ticket v2: provider comparison row + radio, side-aware price highlight (BUY highlights ask), STALE ack, refresh button, slippage shown post-fill |
| TradeDetail (panel) | layout | + provenance block (D2/D12 fields, raw-payload drill) |
| Valuations / Blotter views | tables, filters | + provider column; valuation rows show market_data_timestamp |
| Books | cards, summary | + per-currency subtotals + converted total w/ rate as-of |
| SystemOverview / monitoring | health cards, log tail | + provider ops card (budget spent/remaining, next poll, backoff, RATE_LIMITED state); **all config controls live here** (D24) |
| BusinessOverview | as is | confirmed Phase 6 stretch: desk-home summary — positions + watchlist movers + curve levels; no config controls on business views (D24) |
| Generator view | — | **deleted** (Phase 0) |

Design language: modern quote-board conventions — symbol + mid + Δ + age chip as the headline,
per-provider detail one expansion away, two-sided quotes shown only when real (D11), state as
form (pills/badges) not prose. Everything else stays the existing clean table language.

---

## 8. Engineering properties

The design intentionally preserves these technically important properties:

1. **Provenance drill** now lands on an exact FK (`entry_snapshot_id` → raw payload) — trade →
   quote → raw provider JSON in one join.
2. **Slippage as a first-class record** (seen vs executed, D12) — real order-flow semantics no
   that distinguishes this system from a basic CRUD trading exercise.
3. **Rate limits as visible ops** — now with real numbers (60/min vs 800/day vs 25/day) and a
   RATE_LIMITED state machine.
4. **Cross-official validation** — ECB×NBP FX cross agreed to <0.3% in live probes; NBP
   gram-gold vs XAU/USD ounce conversion; both are one derived number each.
5. **The PLN curve investigation** — upgraded from "documented proxy" to *real monthly OECD
   anchors with an honest lag label*.
6. **EOD-grade honesty** — Alpha Vantage's column saying "EOD (Fri)" instead of fake-LIVE is
   the kind of detail that reads as desk experience.
7. **The API fact sheets themselves** — §2 goes into `docs/market-data.md` nearly verbatim:
   research-before-build, demonstrated.

Deliberately not in scope: websockets, vol surface/Greeks, order matching, auth, brokers,
an instruments table, backtesting (HW6's opening), the replay provider (noted only).

---

## 9. Locked implementation decisions

1. **Repo name** → **`trading-desk`** (D16).
2. **`MAX_ACTIVE_SYMBOLS`** → **25** to start; adding beyond the cap blocks with an
   explanation.
3. **Retention** → **30 days**, presented well on the dashboard; may grow later if it doesn't
   drain the volume budget.
4. **Twelve Data daily ledger** → as recommended (~60% RTH / 40% off-hours).
5. **XAUUSD** → as recommended (keep if a real free key serves metals, else
   NBP-gold-reference only).
6. **BusinessOverview desk home** → yes, as the Phase 6 stretch — with config controls kept on
   technical views only (D24).

---

## 10. Hosted operation, strategies and load visibility

This capability group is based on measurements from the running local stack and Railway
platform constraints checked on 2026-08-17.

### 10.1 Operational requirements

- Keep hosted cost bounded through explicit resource limits, idle suspension and predictable
  provider polling.
- Prevent unbounded database and log growth through write throttling, retention and capacity
  gauges.
- Expose RAM, CPU, thread, queue, stream and database usage through an overview with tabular
  drill-down and log navigation.
- Keep automated investment strategies separate from random trade generation and defer them
  until the real-data execution path is stable.
- Put every non-local deployment behind authentication and expose only one public gateway.

### 10.2 Measured local baseline (3 days uptime, 2026-08-17)

| Container | CPU | RAM |
| --- | --- | --- |
| 8 × Python services | 0.01–8.5% (pricing highest) | **52–71 MB each ≈ 470 MB total** |
| frontend (Vite dev server) | ~0% | 328 MB (a static build ≈ 15–30 MB) |
| postgres | 6.5% | 2.68 GB (cache over a bloated DB) |

**The database after 3 days of the 1 s simulator: 13 GB — of which `valuations` is 38.0 M rows
/ 12 GB.** The user's overflow fear is empirically confirmed on their own machine: pricing
writes a valuation row per affected trade per tick, unthrottled. Everything else is tiny
(spots 146 MB, curves 48 MB, audit 7.6 MB). Two conclusions: (1) hosted RAM footprint is
genuinely ~0.8–1.0 GB once the frontend is a static build and the DB is kept small; (2) a
**valuation write throttle and retention are existential for hosting**, not polish — at local
rates the DB would blow through Railway's volume allowance in about a day.

### 10.3 Railway constraints and cost model

Account (checked in the browser, Aug 17): **Hobby plan** — $5/mo including $5 usage; the
dashboard states the plan allows up to 8 GB RAM / 8 vCPU / 100 GB shared disk (current docs
claim higher compute caps and a 5 GB volume cap for Hobby — the dashboard is authoritative for
this account; our design targets ≤ 2–3 GB either way). **The included $5 is already spoken
for**: existing project `adorable-cat` has used $2.29 this cycle, estimated bill $5.58 —
so everything the trading stack consumes is overage on top.

Platform facts (official docs, verified 2026-08-17):

- **Rates**: RAM ≈ $10/GB·month, CPU ≈ $20/vCPU·month, volume ≈ $0.156/GB·month, egress
  $0.05/GB; private-network traffic free.
- **Serverless sleep is outbound-based**: a service sleeps after **10 min with zero outbound
  packets**; inbound does not reset the timer; it wakes on any inbound traffic (public or
  private) with a small cold start (first request may 502). Explicit sleep-preventers:
  **polling loops, open Postgres connections/pools, active SSE streams**. Consequence: the
  platform can only sleep what the application first quiesces — hence D19's two layers.
  (One community source claims the toggle is Pro/auto-pay-Hobby; verify in the dashboard at
  setup — the fallback is accepting always-on cost.)
- **Cron services**: native crontab per service, ≥ 5 min interval, must exit cleanly (close DB
  connections) or later runs are skipped; billed only for seconds run — ideal for the nightly
  retention sweep.
- **Deploy mechanics**: N services from one repo (root directory + `RAILWAY_DOCKERFILE_PATH` +
  watch paths so a push rebuilds only what changed); `alembic upgrade head` as
  **preDeployCommand on exactly one service** (avoids the migration race); private networking
  is IPv6 — **Bottle's default wsgiref server binds AF_INET only and must be subclassed to bind
  `::`** in all services; internal URLs become `http://${{svc.RAILWAY_PRIVATE_DOMAIN}}:port`;
  no `depends_on` — boot-time retry on DB/peers is mandatory.
- **Logging**: Railway captures stdout/stderr only; container files are ephemeral and **one
  volume attaches to exactly one service**, so the file-tailing monitoring architecture cannot
  be ported as-is → D18's dual log sink.
- **SSE via the edge proxy**: cut after 5 min without data and hard-capped ~15 min → heartbeat
  comments every ~25 s + client auto-reconnect (the snapshot+stream reconciliation already
  handles resume).
- **EU region available** (Amsterdam) — right choice for NBP/ECB latency and the audience.

**Cost estimate** (hosted profile, measured footprint; existing project unchanged at ~$5):

| Scenario | Trading-stack usage | Total monthly bill |
| --- | --- | --- |
| Always-on (no sleep) | ~$10–12 | **~$15–17** |
| Two-layer sleep, ~75% idle | ~$3–4 | **~$8–10** |
| Sleep + `adorable-cat` paused/removed | ~$3–4 | **~$5–7** |

Verdict: **Hobby suffices** — capacity is a non-issue at ~1 GB; the question is only tolerated
overage. Expect roughly **$3–5/month extra** with sleeping working, ~$10–12 extra without.

### 10.4 Decisions D17–D22

**D17 (deferred) — Automated trades use a thin strategy runner, not a random generator.**
A future `strategy-service` runs explicit
signals on watchlist symbols: **SMA-crossover / trend-following** on Finnhub equities, and
**fair-value-vs-market divergence** (pricing-service fair value vs market quote) where curves
price the instrument. Small fixed notional, paced within API budgets, trades into a dedicated
`STRATEGY` book, **every intent carries its signal rationale in the frozen terms** ("SMA(10/30)
crossed up @ 189.20, FINNHUB") — provenance meets strategy. Closes occur on the opposite
signal; on/off state and parameters remain visible in the technical UI. Alpha/beta versus SPY
measures whether the strategy outperformed its benchmark. Random trade generation stays
removed because it provides no explainable signal or execution provenance.

**D18 (new) — One `DEPLOY_PROFILE`, two honest modes.**
`local` (today's behavior) vs `hosted`: log level WARNING with structlog **writing JSON to
stdout** (Railway's only capture) while each service also keeps a bounded **in-memory ring of
recent log lines exposed via a `/logs/tail` endpoint — monitoring polls that instead of tailing
files**, preserving the existing bounded-buffer semantics;
relaxed poll cadences (tier-1 ~60 s); SSE heartbeats ~25 s; frontend poll intervals widened;
IPv6 (`::`) binding + `PORT` contract everywhere (harmless locally); `python:slim` multi-stage
images (~1.7 GB → ~200 MB, faster deploys). *Rejected:* a Railway-only fork of the logging
stack (one architecture, two sinks — the monitoring reader changes its source, not its model).

**D19 (new) — Two-layer auto-pause: the app quiesces so the platform can sleep.**
Layer 1 (app): market-data-service tracks activity (open SSE clients + last non-health API
read). After `IDLE_PAUSE_MINUTES` (default 12) of none, it flips a shared IDLE state: all
schedulers pause (also saving provider API budgets), loops go dormant, and **every service
disposes its DB connection pool** — because Railway's sleep rule counts outbound packets, and
open Postgres connections/polling loops explicitly prevent sleep. Layer 2 (platform): with the
app quiet, Railway Serverless sleeps each service ~10 min later; **any visitor wakes the chain**
(request → Caddy → services → pools reconnect → schedulers resume), with a frontend "waking
up…" state for the cold-start seconds. The IDLE/ACTIVE state is shown on the dashboard —
the pause is a feature you can watch, not a hack. *Rejected:* platform sleep alone (provably
never triggers under polling), app pause alone (saves API budgets but not a cent of RAM
billing).

**D20 (new) — Data ceilings, now evidence-based.**
(1) **Valuation write throttle**: persist at most one valuation row per trade per
`VALUATION_WRITE_INTERVAL` (hosted ~5 min, local ~1 min); the live UI is unaffected (it reads
SSE), the DB keeps a sampled history — kills the 38 M-row failure mode at the source.
(2) **Nightly retention sweep as a Railway cron service** (quotes history, valuations, audit
beyond their windows; VACUUM; clean exit).
(3) **DB gauge on the dashboard**: allocated vs used volume, per-table sizes, days-to-full
projection and a warning threshold.
(4) **Admin reset**: a token-guarded `POST /admin/reset-demo-data` truncating market history +
valuations + audit (books/trades kept; option `full=true` reseeds everything) — the user's
"reset full data" ask, safe behind auth.

**D21 (new) — The technical load dashboard.**
Each service self-reports via stdlib only (`resource.getrusage`, `os.times` deltas,
`threading.active_count`): RSS, CPU%, threads, uptime, plus domain gauges (SSE clients, queue
depth, cache sizes, budget spend, RATE_LIMITED/IDLE states). Monitoring aggregates into
`/system-load`; a new **System load** panel on SystemOverview provides a visual overview,
tabular deep-dive and click-through to the service's logs. Local `docker stats`
comparison goes into `performance.md` (Phase 7's stress-test numbers become this panel's
baseline). *Rejected:* psutil (dependency for what stdlib provides) and Docker-API scraping
(unavailable on Railway; self-reporting works in both worlds).

**D22 (new) — Railway topology: one public door, everything else private.**
Services: Caddy gateway (static Vite build + reverse proxy to private services + **basic-auth**),
8 backend services private-only (IPv6 mesh),
managed Postgres + volume, cron sweep service, preDeploy migration on market-data-service.
EU West region. Egress ≈ one gateway's worth; internal traffic free. The old repo stays
local-only; the fork deploys. *Rejected:* exposing each service publicly (8 auth surfaces, more
egress, contradicts his security stance).

### 10.5 Hosted-operation sequence (~3–4 days)

- **8.1 Portability** *(~1 d)* — IPv6 bind + `PORT`, boot-time retries, `DEPLOY_PROFILE`,
  stdout JSON logs + `/logs/tail` ring, SSE heartbeats, slim images. All local-safe; lands in
  the main branch.
- **8.2 Gateway** *(~0.5 d)* — Caddy service: static build, `/api/*` reverse proxy, basic-auth,
  same-origin paths (the Vite proxy contract carries over unchanged).
- **8.3 Railway provisioning** *(~0.5 d)* — project, services with root dirs + watch paths,
  variables via references, preDeploy migration, Postgres, cron sweep, serverless toggles,
  EU region; verify the serverless toggle exists on Hobby.
- **8.4 Idle & ceilings** *(~1 d)* — D19 quiesce/wake, D20 throttle + sweep + gauge + admin
  reset; observe an actual sleep/wake cycle in Railway metrics.
- **8.5 Load dashboard** *(~1 d)* — D21 end-to-end; baseline numbers into `performance.md`.
- ~~**8.6 Strategy runner v0**~~ — deferred until the hosted real-data system is stable; D17
  records the intended design.
- **Acceptance check:** the application wakes from sleep through the public gateway, the load
  dashboard shows each container's RAM/CPU and the live database gauge, and measured monthly
  usage fits the selected plan.

### 10.6 Open deployment decisions

8. **`adorable-cat`**: keep running (bill ~$8–10 with sleep) or pause/remove it (~$5–7)?
   It currently consumes the entire included credit.
9. **Timing**: provision hosting after the local hardening sequence, or bring gateway and
   provisioning work forward?
10. **Access**: use one shared basic-auth credential or issue per-user credentials?
11. **Serverless on Hobby**: if the toggle turns out to be plan-gated, accept ~$10–12/mo
    overage always-on, or fall back to manually pausing the Railway project when not in use?
