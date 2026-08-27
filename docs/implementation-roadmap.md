# Implementation roadmap — real-data trading system

This roadmap records capability boundaries, dependencies, technical decisions and acceptance
checks for the real-data trading system. It is a forward-looking working plan; implemented
behavior is authoritative in the phase reports and the reference sheets (`architecture.md`,
`market-data.md`, `configuration.md`).

The migration starts from `trading-microservices`, removes synthetic/static market flows and
rebuilds market data around real providers. Provider facts come from live probes performed on
2026-08-17, the Alpha Vantage readiness probe on 2026-08-26, or provider documentation and are
marked accordingly. Revalidate documented limits when registering production keys.

The original core sequence was budgeted at roughly 14–15 focused engineering days. With
Phase 5 delivered, **Phase 6 is the single remaining project phase**: it adds the final required
quote source, closes the small contract gaps and verifies the whole application as one coherent
system. Hosting, strategies and product experiments remain optional post-acceptance extensions,
not more phases required for the next review.

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
| Data | FX fixings: table A (`mid`), **table C (`bid`/`ask`)**, gold (PLN per 1 g) | Yield curves **AAA (`G_N_A`) and all-bonds (`G_N_C`)**, tenors `SR_3M…SR_30Y`; EXR FX fixings | `DGS1MO…DGS30` Treasury curve; SOFR/DFF |
| Verified Mon Aug 17 | table `158/A` dated 08-17; C: bid 3.6804 / ask 3.7548; 157/C was Friday — clean business-day sequence | YC as-of 08-14 (Fri, publishes next TARGET day ~noon); EXR 08-17: USD 1.1593, PLN 4.3063 | DGS through 08-13 (1–2 business-day lag); SOFR through 08-14 |
| Auth / limits | none; 93-day range cap | none; fair use | free instant key; 120 req/min |
| Format note | plain JSON | **use `format=csvdata`** — SDMX-JSON nests values ~5 levels deep; CSV is stdlib-parseable | JSON; values are *strings*, missing = `"."` |

### The ten consequences that shape v2

1. **No free Group-A source gives equity bid/ask.** The brief's bid/ask-mapping decision is the
   *main case*, not an edge case → D11.
2. **Alpha Vantage equities are EOD** (date-only timestamp). Pretending otherwise would be a
   freshness lie → the `quote_grade` concept (REALTIME / EOD / REFERENCE), D3.
3. **Twelve Data's real constraint is the daily cap** (800), not the per-minute one → budget
   governor spreads credits across the day, D7.
4. **Finnhub has no free FX** → per-provider capability differs by asset class → the fourth
   freshness state **UNSUPPORTED** (a capability fact, distinct from MISSING data), D3.
5. **Two Polish reference observations do not make a forward curve.** FRED/OECD publishes a
   monthly 3M interbank observation and a 10Y government yield, but interpolating between them
   creates false precision rather than a defensible IRS projection → the set is retired in D6.
6. **ECB serves two genuine EUR government curves** (verified keys), but those are bond curves,
   not floating-index projection choices. The ECB×NBP FX cross-check agreed to <0.3% today →
   the disagreement-in-bps idea works on official data too.
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
- **Scenarios**: `full-flow.http` (generator-driven); final provider scenarios are completed in
  Phase 6.
- **Catalog**: `INSTRUMENT_CATALOG` is *not* generator-only — trade-action validation, term
  schemas and the ticket depend on it — so it is **replaced** by the symbol master (D4) in
  Phase 1, not deleted in Phase 0.

Compose lands at 8 services: postgres, db-migrations, market-data, pricing, monitoring, books,
trade-action, blotter (+ frontend). The future strategy milestone's runner will be a new, purpose-built service.

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
swept by a retention job (`SNAPSHOT_RETENTION_DAYS`, default 90). `market_data_curves` (+ new
`market_data_curve_points`) = curve sets upserted by (provider, curve, as_of_date) — ≤ one set
per source per day *by construction*. Growth math at 25 active symbols: Finnhub ≤ ~10k rows/day
worst case, Twelve Data ≤ 800, Alpha Vantage ≤ 25, curves ≤ ~40 points/day → trivial for
Postgres, flat under retention. This answers "fresh enough without overflowing the DB" with
numbers.

**D6 (upgraded) — Curve catalog, now fully verified.**
- `USD_GOVERNMENT_BONDS` — 11 FRED DGS series, 1–2 business-day lag; par-treated-as-zero documented.
- `EUR_GOVERNMENT_BONDS_AAA` / `EUR_GOVERNMENT_BONDS_ALL` — ECB `G_N_A` / `G_N_C` (both keys verified),
  `SR_3M…SR_30Y`, `csvdata` format; deliberately limited to EUR bond context/discounting.
- `EUR_RISK_FREE` / `USD_RISK_FREE` / `PLN_RISK_FREE` — EIOPA monthly risk-free term
  structures, kept as a coherent discount source for the three model currencies. Their
  source derivations and any extrapolated points remain visible. IRS tickets use one eligible
  same-currency risk-free curve for both discounting and projection and label this explicitly as
  a single-curve approximation.
- `PLN_REFERENCE_PROJECTION_3M` is retired. It mixed one monthly 3M interbank observation with a
  10Y government yield and linearly interpolated the middle, so its matching tenor label implied
  precision it did not have. Government-bond curves remain bond-only; same currency alone does
  not qualify a curve to forecast an IRS index.
- **The tenor dimension, honestly:** IRS terms retain `floating_rate_index_tenor` for contract
  payment mechanics and disclosure, while the public selector makes no claim to be calibrated to
  that 3M or 6M index. The numerical pricing interface still accepts separate discount and
  projection curves so a licensed, index-calibrated source can restore a genuine two-curve
  contract later.
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
next window. `429`/limit bodies classify as `RATE_LIMITED` (own
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

**D9 (superseded by D1) — trade-generation-service is removed in Phase 0.** Future automated
strategies get a fresh, purpose-named service later. *Rejected:* keeping an idle shell — dead weight in a
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
assumed spread (invents data — the brief explicitly permits empty fields); trading at mid when a
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
(all alpha/beta needs) track the index. The estimator itself survives unchanged, as the
pre-fork decision log bet it would (preserved in the archived repository).

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
this provider* — e.g. `ALPHA_VANTAGE_DAILY_BUDGET=22` (90% of the published 25/day free tier),
`FINNHUB_TIER1_POLL_SECONDS=15` (60/min free tier below its safe utilization
across a 25-symbol set), `TRADE_PRICE_TOLERANCE_PCT=1.0` (fills rejected beyond 1% of the seen
price), `IDLE_PAUSE_MINUTES=12` (inside the 10–15 min window; above Railway's 10-min sleep
threshold). `docs/configuration.md` mirrors the full table with per-profile defaults. The
counterpart rules: **code carries no comments** — it is written to be self-explanatory, with
all rationale in `docs/`; the **README shrinks to only what a stranger needs** to run and test
(the brief's required sections, kept lean, linking into `docs/` for approaches and decisions);
and **config controls in the UI live on technical views only** (SystemOverview/monitoring),
never on business screens. The six provider clients follow **one enforced module shape** —
same base class, same
client/normalizer pairing and same method names — so learning one provider path transfers to
the others.

**D25 — Verification = scenario flows + scenario load tests;
no unit-test suite.** The house convention stays: `scenarios/*.http` flows verify behavior
end-to-end through the real system (completed for the provider world in final Phase 6). The
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
exercises the same logic through the real system instead. *(Owner ruling 2026-08-23:
structural/contract tests are also out — the load scripts stay because they are the
brief's stress test. The existing provider registration and end-to-end scenarios are the useful
contract checks; no extra inheritance demonstration is required.)*

**D26 (new) — Reference rows are a fourth board origin, never tradeable.** NBP/ECB fixing
pairs join the board with a `reference` origin flag (alongside watched/held/benchmark) but
never the tradeable universe: `/instruments` derives from watched symbols only (held-only
symbols remain pollable for existing positions), and
the ticket never offers a REFERENCE-grade row. Corollary pinned in code: watchlist choices
and symbol search offer **Group A only** (`shared/providers.QUOTE_PROVIDERS`, not "all
wired feeds") — otherwise `POST /watchlist {providers: ["NBP"]}` becomes legal for FX the
moment NBP registers as a wired feed. *Rejected:* reference pairs as watchlist items —
user-owned scope would mix with system-owned reference data, and removing one would
silently break currency conversion.

**D27 (new) — The reference universe is configured defaults ∪ reportable-trade currencies.**
Defaults: NBP `EURPLN`, `USDPLN`, gold; ECB `EURUSD`, `EURPLN`. Settlement currencies of
active and closed trades auto-join when the source publishes them, so realized P&L remains
convertible after the final position closes; when no official path exists the
resolver says so and the UI shows the unconverted subtotal with the reason. *Rejected:*
ingesting full tables as board rows (~35 noise rows per source) — the full raw table
response is retained in each row's snapshot anyway.

**D28 (new) — Currency conversion is a display overlay.** The D23 resolver serves rates
with full provenance (`GET /fx/rates?to=<CCY>` on market-data); the browser multiplies for
display. Nothing converted is ever persisted — positions and valuations keep their
settlement currency (the review's rule: convert at the portfolio level only) — and no
service calls another service's API for it. *Rejected:* server-side enrichment in
blotter/pricing (couples services or duplicates the resolver for numbers that are only
displayed).

**D29 (new) — Display precision.** Board and ticket render an asset class's display
decimals (equities 2 dp); Quote Detail, snapshots, streams and all money math keep the
provider's exact value. Context: Twelve Data publishes equity closes like `309.35001`; the
pipeline preserves it exactly (`Decimal(str(...))` at the contract boundary), so the tail
is the provider's own published value, not an artifact — display rounding removes the
false-alarm reading without touching D11's stored-as-received guarantee. *Rejected:*
rounding at ingest (destroys D11); raw everywhere (reads as a bug — it did, live).

**D30 (new) — NBP table C (official bid/ask) is deferred.** Table A's mid is what
conversion and display need; feeding C's bid/ask into the same row would win `build_quote`
precedence over A's `reference_mid` and change what the FX resolver reads. Recorded as a
stretch with that design question; revisit only if the review asks for official buy/sell
rates.

**D31 (new) — Curve raw provenance lives at the set level.** One fetch = one raw source
response = one `raw_payload` on `market_data_curves`; points keep `source_series` +
`source_as_of` (NULL series marks a derived point). *Rejected:* duplicating the same blob
per point.

**D32 (new) — the curve's stored label is a small documented text vocabulary**
satisfying the brief's column sketch. It shipped as `curve_basis`, naming how the
numbers were derived rather than a modelling shorthand, because that is the fact the
role rules read. *Rejected:*
modeling discount-vs-projection as a curve property — that is a per-trade choice and lives
in the frozen terms.

**D33 (new) — The audit matrix goes brief-literal, bounded.** Fetch success is
audited per external call with a minimal payload (provider, endpoint class, status,
duration — never bodies; ≤ ~6–8 k rows/day at cap, retention-swept); `QUOTE_WRITTEN` moves
from first-quote-only to **change-only writes** (the same discipline as history rows);
curve-set writes and `VALUATION_BLOCKED` join the matrix. *Rejected:* mapping the
brief's fetch event onto the structured log alone — defensible, but it argues with an
explicit requirement list for no real saving.

**D34 (new) — The valuation write throttle closes in final Phase 6.** At most one
persisted valuation per trade per `VALUATION_WRITE_INTERVAL_SECONDS` (local default 60 s);
SSE stays per-tick so the UI loses nothing; each persisted row is auditable. The 38 M-row /
12 GB three-day local measurement (§10.2) makes this a current-phase correctness ceiling,
not hosting polish. *Rejected:* leaving it hosted-only — the local database provably blows
up within days, and a review window can span days.

**D35 (revised) — Free-tier surface is intentional, not exhaustive.** Phase 5 keeps the
small comparable quote contract needed for execution: mark/side prices, previous close,
two clocks, grade, state and provenance. Day/52-week ranges, volume, order-book depth and
open interest stay out even when one response happens to contain them; their meanings and
coverage differ and they do not improve this phase's trade flow. Every later capability
must pass the runbook §6 five-answers bar (exact measure, instrument scope, interval/as-of,
units, entitlement) and belong to that later phase before it enters schema or UI.
*Rejected:* adding fields because an endpoint already returned them — zero extra requests
does not mean zero product or teaching complexity.

---

## 5. Target architecture

### market-data-service layout

```
app/
  api.py           # /providers, /providers/<p>/health, /market-data/{snapshot,quotes,stream,refresh},
                   # /curves(/…,/refresh), /symbols/search — plus SSE
  providers/registration.py      # one runtime capability contract
  providers/<provider>/          # client + normalizer/curves + feed wiring
  providers/base.py              # urllib transport and typed provider errors
  quote_service.py # board/watchlist/refresh use cases
  quote_store.py   # current board + change-only quote history
  curve_service.py # curve read/refresh use cases
  curve_store.py   # curve set + point persistence
  scheduler.py     # maps/loops derived from provider registrations
  budget.py        # rolling minute budgets + daily ledgers (surfaced on /providers)
  retention.py     # protected quote-history retention sweep
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

Each phase ends with an executable acceptance check, its phase report, and fact-only
updates to the reference sheets.

### Replan checkpoint — brief + design review *(2026-08-22)*

The current implementation is ahead of the old phase labels: the two-provider ticket,
server-priced execution, provider frozen on the trade, provider-bound valuation and close,
change-only quote history and the provider operations surface are already present. The former
Phase 4 trading-flow work is therefore part of the delivered Phase 3a vertical, not future work.
Phase 3b has now closed its route/scenario drift and fresh-stack review boundary.

The replan follows five direct signals from the review and the brief:

| Evidence | Planning consequence |
| --- | --- |
| Review: compare the provider event time, not only the local receive time. | Preserve the two-clock contract and make both clocks visible in every provider/curve review. |
| Review: keep the selected quote card visible while its history scrolls. | Keep the shipped fixed quote card and independently scrolling tape; do not redesign the praised side-panel model. |
| Review: positions retain settlement currency; only portfolio reporting converts to one currency. | Put NBP/ECB reference FX and a provenance-carrying reporting-currency resolver before portfolio aggregation. |
| Review: connect NBP and the other central banks next; the current design is functionally sound and flexible. | Official sources move ahead of strategy work and broad refactors. Add providers through the existing boundary. |
| The brief (pp. 2–14): all six sources, the listed Market Data routes, three-provider ticket, same-provider PnL, official curves, audit events, README and repeatable tests are required. | None of Alpha Vantage, NBP, ECB, FRED, contract/audit closure or verification is optional for the v2 finish line. |

The review also raised volume, visible order-book depth and open interest. Those
are different measures and are not v2 acceptance criteria. Phase 3b records the provider
capability finding, but no field or chart ships until its semantics and upstream availability
are verified. Sparse application observations also remain a discrete history tape; they are not
reintroduced as a continuous market chart.

### Replan v2 — full review pass + demo debrief *(2026-08-23)*

A second, deeper pass over both review sessions against the whole plan (full signal inventory and
compliance matrix retained outside the repo) changed four things:

- **Two signals adopted**: FX pair prices must name their unit (own catch during the demo)
  → Phase 4; and the planned shared external feed — participants plug into it *as one more
  provider* — becomes an explicit extensibility probe → Phase 6.
- **Tests ruled out** (owner decision): no structural/unit tests; D25 amended above. The
  final-phase load scenarios stay — they are the brief's stress test.
- **The demo's live bugs become Phase 4 inputs (B1–B5)**, folded into Phase 4 below with
  their code-level hypotheses.
- **A standing phase template** now governs every remaining phase so each is one complete,
  reviewable step.

### The standing phase template

1. **Discover and bound** — compare the assignment, current roadmap and running system;
   classify work as required now, already delivered, explicitly excluded or optional later.
   Trace each new value end to end, name its semantic owner, verify provider facts against
   current official documentation and a minimal live probe, and decide persistence/migration
   before implementation. A stale task is rewritten here rather than implemented literally.
2. **Verify** — re-run the previous phase's gate on both retained and fresh state before building.
3. **Build the smallest vertical slice** — domain/capability contract, provider adapter,
   normalized storage/publication, pricing/trading consumer, UI state, then ops/audit visibility.
   Reuse an existing boundary instead of adding a speculative abstraction.
4. **Evidence** — a phase scenario `.http` flow plus a retained evidence record in the
   phase-3b format (commit, market session, IDs, both clocks, probes).
5. **Browser pass, driven by a real scenario** — every touched view exercised in the
   browser against at least one realistic scenario opened end to end through the running
   services (real books and trades in the states the feature claims to handle — mixed
   currencies, several providers — cleaned up afterwards), never just whatever state the
   stack happens to be in. The pass hunts behavior bugs, not only rendering: recompute
   every displayed aggregate independently and compare it against the screen (a headline
   must equal its rows' arithmetic); watch time-dependent behavior across at least one
   full cycle — a poll cadence, a countdown, a window boundary — rather than one
   snapshot; after each user action watch what follows within its expected latency (an
   added symbol quotes, a close settles); walk the empty, single-item, mixed,
   missing-data and market-closed states. UX/UI reviewed deliberately (layout, copy,
   error states, side-panel behavior — the established design language), zero console
   errors or warnings, screenshots retained for the phase report.
6. **Docs & report, after implementation, in the same change** — the
   `phase-reports/phase-N.md` is the detailed record: every decision (chose / rejected /
   why), the difficult implementation concepts taught step by step, **with a mermaid
   diagram wherever a picture genuinely aids understanding** — each phase below names its
   candidate diagrams so this is planned, not improvised. The reference sheets
   (`market-data.md`, `configuration.md`, `architecture.md`) and the README
   operating-decision and data-flow rows get fact-only updates — new endpoints, knobs,
   cadences, tables; all explanation stays in the report.

### Phase 0 — Fork & deep clean *(complete)*
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

### Phase 1 — Contracts & schema *(complete)*
`shared/`: normalized-quote + curve-point contracts, provider registry + capability matrix,
`freshness.py` (four states, grades), `symbols.py` (conventions; catalog consumers migrated).
One hand-written migration: board uniqueness + quote columns (bid/ask/last/mid/basis/two
clocks), history reshape, curve tables, trades/valuations columns (D2), `watchlist_items`.
Start `docs/market-data.md` seeded with §2's fact sheets — the domain analysis is pre-written.
**Exit:** migration up/down clean on a fresh DB.

### Phase 2 — Finnhub vertical slice *(complete)*
`clients/base.py` (body-aware error classification), Finnhub client + normalizer, scheduler v1
(active set, token bucket, market-status awareness), board upsert + change-only history +
provider-tagged SSE, endpoints (`/providers`, health, quotes, refresh), pricing cache keyed
(provider, symbol), UI board shows provider + age from `provider_timestamp`.
**Acceptance check:** live AAPL on screen with honest age; a manual trade valued off Finnhub through
the (provider, symbol) cache.

### Phase 3 — Watchlist, second provider and provider-bound trading

Phase 3 is split by review state. **3a** is the delivered two-provider workflow; **3b** closes
its executable review contract before another provider is added.

**Phase 3a — core multi-provider workflow *(complete in code)*:**
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

**Phase 3b — review closure *(complete 2026-08-22)*:**

- The executable examples use the implemented trade-action route, provider-specific history and
  detail paths. The brief's direct port-8001 contract is canonical while short aliases
  remain compatible:
  `/market-data/snapshot`, `/market-data/quotes`, `/market-data/quotes/<provider>/<symbol>`,
  `/market-data/stream`, `/market-data/stream/<provider>` and
  `POST /market-data/refresh`.
- The quote detail keeps its current card fixed while only the observation tape scrolls;
  Provider time and Received remain visible together.
- The Dockerfile PATH is valid. A fresh isolated Compose database reached migration head and the
  two-provider open/value/close path, canonical/alias routes, filtered SSE, frontend and static
  checks passed.
- The market-data reference distinguishes traded volume, displayed depth and derivatives open
  interest for the wired endpoints without adding an unsupported UI field.

**Acceptance check — met:** the fresh Compose stack passed the repaired scenario request path
without hand-edited URLs; Finnhub and Twelve Data each opened, valued and closed a trade on their
own frozen feed; the selected quote summary kept its bounds while the observation tape scrolled.
The retained evidence and review prompts are in
`docs/phase-reports/phase-3b.md` and `docs/validation-runbook.md`.

### Phase 4 — NBP/ECB reference FX and the reporting currency *(complete 2026-08-23)*

Delivered as planned, including the demo debrief (B1–B5), the presentation-review round
(benchmark card redesign, UI copy pass — the no-purpose-captions ruling now codified in
AGENTS.md) and the weekend market-feed evidence. The full walkthrough, decisions and retained evidence are in
[`phase-reports/phase-4.md`](phase-reports/phase-4.md); the section below is preserved as
the plan it was executed against.

**Goal.** The first two official sources — NBP FX fixings + gold, ECB euro reference
rates — through the *same* gateway, normalizer, board, SSE and ops surfaces as Group A,
plus the D23 FX resolver turning multi-currency books into one explicitly chosen
reporting-currency total with full provenance. Positions never convert; reporting does.
Decisions: D26–D30.

**T4.0 Verify + demo debrief *(0.5 d)*.** Fresh-stack 3b gate (`provider-trading.http` +
runbook §§1–5), then close the 2026-08-21 demo-review findings:

- **B1 — Twelve Data refreshed late; age did not zero at the expected 15 min** (observed
  ~21:02 Warsaw, US market open). Ranked hypotheses, each checkable from existing
  logs/ops data before any fix: (1) the paced interval silently grows past the knob —
  `paced_interval_seconds() = max(900, round(active_window × symbols / daily_budget))`
  = 60 s/symbol at defaults, so >15 Twelve Data symbols means >15 min, and adding symbols
  mid-session lengthens the *next* batch with nothing on screen explaining it; (2)
  minute-bucket contention — searches spend the same 7-token bucket the batch needs
  (`try_take(len(chunk))`), and all symbols share one synchronized due-time, so the board
  ages and jumps in lockstep; (3) age counts from `last_quote_at` (the provider's
  last-trade clock), so a successful poll of a thin symbol never zeroes it — correct data,
  surprising display. Diagnose from `provider_http_response` inter-batch gaps + ops-card
  cadence + token spend; then land the honest fix: **"next batch in Xs · cadence Y min
  (N symbols on the daily ledger)"** on the ops card and row tooltip, stagger per-symbol
  due-times so the board refreshes rolling, and document age-vs-poll in the guide.
- **B2 — cross-provider price differences (the Tesla moment)** — expected behavior,
  answered by the two clocks; retain the raw-payload evidence that `309.35001` arrives as
  Twelve Data's own published string (D29 context) and let D29's display rounding remove
  the false-alarm reading.
- **B3 — a freshly added watchlist symbol showed no price during the demo.** A
  Twelve-Data-only add legitimately waits for the next batch — up to a full paced
  interval. Fix: one targeted budget-aware refresh on watchlist add (the D7 mechanism
  already prescribed for ticket-open) + honest MISSING copy: "waiting for first quote —
  next TWELVE DATA batch ≤ N min."
- **B4/B5** land in T4.3 (FX unit labels; search results label their quote currency so
  the list cannot be misread as holdings — the TWD confusion).

Ride-along doc hygiene: fix phase-2's dead plan link; phase-3a review record indexed
(docs reorganization, 2026-08-23).

**T4.1 Clients + feeds *(~1 d together with T4.2)*.** `clients/nbp.py` (table A mids +
gold, JSON) and `clients/ecb.py` (EXR via `format=csvdata`); one Template-Method extension
to `clients/base.py` — a response-decode hook (default `json.loads`) so ECB parses CSV via
stdlib `csv` without touching the base algorithm. NBP 404 = "fixing not published yet" →
data condition, never provider failure; ECB empty/short CSV likewise. `nbp_feed.py` +
`ecb_feed.py` register in the same `scheduler.FEEDS` registry (provider streams,
`/providers`, refresh routes come free). Their loops are **calendar windows**, not
cadences: poll inside the publication window (NBP A ~11:45–12:15 CET business days; ECB
EXR ~16:00 CET TARGET days) until a **new as-of** appears, then sleep to the next window;
a bounded off-window confirmation poll keeps `received_at` honest. No token bucket —
keyless, unlimited sources keep the status machine without invented budgets. Reference
universe per D27; rows go through the existing `build_quote` (reference_mid, grade
REFERENCE, `provider_timestamp` = the as-of) and `store_quote`/`publish_quote`, raw table
responses landing in the row's snapshot. Needs `tzdata` for `zoneinfo` in slim images.

**T4.2 Freshness for fixings.** No new states: a reference row's `stale_after_seconds` is
computed from the source calendar (time to next expected publication + grace), so a Friday
fixing stays current through the weekend and STALE means a genuinely missed publication.
`market_open` stays NULL; the UI renders REFERENCE age as "as of 2026-08-22", not a
seconds counter.

**T4.3 Resolver + surface *(~0.5 d + 0.5 d)*.** `shared/fx.py` per D23 (identity → direct
or inverse official rate → one cross via EUR → cross via PLN; a path never mixes sources;
`Decimal`; "no official path" is an honest value), served as `GET /fx/rates?to=<CCY>`; the
browser converts for display (D28). UI: an **Official rates section** beside the benchmark
strip (the established layout, no redesign) — NBP + ECB rows with mid, as-of, both clocks,
provenance drill, and the **EUR/PLN NBP-vs-ECB cross-check chip in bps**; a reporting-
currency selector on Valuations and Books (explicit user choice, remembered per browser)
with per-currency subtotal rows and one converted total labeled "→ PLN via EUR · ECB · as
of 2026-08-22"; unconvertible currencies stay as labeled subtotals; **FX unit labels
everywhere a pair renders** ("4.2610 PLN per EUR"); search-result quote-currency labels;
ops cards for NBP/ECB (keyless badge, window schedule, next window, last as-of).

**T4.4 Evidence + browser pass + docs *(~0.5 d)*.** `scenarios/reference-fx.http`
(official rows via canonical routes, provider-filtered stream,
`POST /market-data/refresh?provider=NBP` table refresh, `/fx/rates`, the cross-check
read) + evidence record. Browser pass over Market Data, Valuations, Books, System
Overview, the ticket (reference rows absent from provider options) and Logs. Docs per the
standing template; candidate diagrams: the reference-data flow (source → window poller →
board/SSE → resolver → UI label), the conversion-path precedence tree with a worked
USD→PLN example, and a publication-calendar timeline (why Friday survives the weekend).

**Acceptance check:** NBP and ECB rows show the last official business-date fixing with
both clocks and raw provenance one drill away; the EUR/PLN cross-check chip reads in bps;
a USD+EUR book shows per-currency subtotals and no combined number until a reporting
currency is chosen — then exactly one converted total labeled with rate, path, provider
and as-of; a weekend read renders Friday's fixing current and a missed publication goes
STALE after grace; FX pairs name their unit; a REFERENCE row can never be selected on the
ticket and a forged NBP intent is refused with the reason; NBP network failure degrades
only NBP's card; B1 explained by the ops card's true cadence story; B3 gone (an added
symbol quotes within seconds or says when it will); browser pass clean on every touched
view.

**Out of scope:** curves (P5), FRED (P5), best-rate logic (D13 stands), NBP table C
(D30), converted persisted values, new chart types, intraday history.

### Phase 5 — rate curves, model-priced execution, and the curve catalog *(complete 2026-08-26)*

The original task list is intentionally not retained here: it contained session widgets,
history backfill, a locally configured NBP flat curve and a New York Fed short-end series
that were later removed as unrelated or misleading. The complete shipped record and the
reasons are in [`phase-reports/phase-5.md`](phase-reports/phase-5.md); the Polish defense
guide is [`phase-reports/phase-5-krzywe-i-kod.md`](phase-reports/phase-5-krzywe-i-kod.md).

**Delivered boundary.** Finnhub and Twelve Data provide tradeable quotes. NBP and ECB
provide official FX/reference observations. FRED, ECB and EIOPA
provide the seven intentional curves. Bonds, IRS and equity-underlying European options
are model-priced from validated terms and selected curves. The server re-reads market data,
recomputes before execution and freezes provenance. Alpha Vantage remains Phase 6.

**Deliberate simplifications.** One schema-only migration adds curve basis/raw provenance
and instrument identity; it contains no data backfill or cleanup DML. Disposable local data
was reset once, after which the live feeds repopulated current curves and application flows
created the demonstration state. There is no quote session-statistics schema, synthetic
spread, fake NBP curve or realized-overnight "forward" curve. The chart uses linear maturity
years and an explicit auto-scaled rate axis. The ticket uses short curve choices plus separate
labeled facts.

**Asset-language acceptance.** Equity uses whole-share quantity; FX uses base-currency
notional; commodity uses quoted-unit quantity; bonds show PV per bond; IRS shows direction,
notional and full-position NPV rather than internal `BUY × 1`; options show an equity
underlying mark and a multiplier-1 model premium. A closed benchmark says `last session`
versus `prior session close`, not `today`. Futures remain absent because this phase has no
provider/model for them.

**Acceptance check.** Exactly seven intended curves are ingested by runtime feeds; currency/role/product/
index guards reject incompatible selections; bond, IRS and option preview and execution
use the same shared math; a curve tick refreshes affected tickets and valuations; point
provenance is inspectable; the one schema-only migration reaches head on a fresh database;
full-width and narrow browser passes are clean for Market Data and every asset ticket.

**Out of scope.** Alpha Vantage, complete three-provider comparison, bootstrapping,
licensed term-index curves, vol surfaces, historical analysis, session analytics and
futures.

### Phase 6 — final project closure *(delivered 2026-08-26)*

**Goal.** Make the next review the final project review. Add Alpha Vantage as the third
tradeable quote source, close the small correctness and compliance gaps left by earlier phases,
and verify the complete application from provider response to persisted trade, revaluation,
close and portfolio presentation. This phase does not redesign working architecture.

**Status.** Delivered. The authoritative handoff and measured evidence are in
[`phase-reports/phase-6.md`](phase-reports/phase-6.md), the integrated executable path is
[`../scenarios/full-provider-flow.http`](../scenarios/full-provider-flow.http), and bounded
load/growth evidence is in [`performance.md`](performance.md). Everything below remains the
acceptance plan that produced that shipped boundary; later headings are optional extensions.

**T6.0 Discovery and frozen scope.** Re-run the Phase 5 gate on retained and fresh data. Check
the assignment against the running routes, UI and schemas; record every remaining item as
required, already delivered, deliberately excluded or optional extension. Re-probe the current
Alpha Vantage free entitlement before coding: published limits and endpoint grades can change.
No schema migration is expected; if discovery proves one unavoidable, this phase may contain at
most one schema-only migration and no business-data cleanup DML.

**Readiness evidence (2026-08-26).** The configured key returned an AAPL `GLOBAL_QUOTE` with a
latest trading date and returned EUR/USD rate, bid, ask and full refresh timestamp from
`CURRENCY_EXCHANGE_RATE`. A request made too quickly returned HTTP 200 with an `Information`
body asking the client to slow down; the same FX request succeeded after spacing. The official
[support page](https://www.alphavantage.co/support/) states 25 requests/day for the standard free
service, and the [endpoint documentation](https://www.alphavantage.co/documentation/) defines the
payload contracts. Therefore Phase 6 must guard
both one daily ledger and provider-wide request spacing, and must classify the body before
normalization.

**T6.1 Alpha Vantage vertical.** Add
`providers/alpha_vantage/{client.py,normalizer.py,feed.py,__init__.py}` and one
`ProviderRegistration`, reusing the existing shared transport, normalized quote, scheduler,
store, SSE and provider-runtime contracts. There is no new inheritance contract, client
hierarchy or generic scheduler rewrite.

- `GLOBAL_QUOTE` supplies US equity/ETF **EOD** marks. Its latest trading date is displayed as
  `EOD (date)`, never `LIVE`, and missing bid/ask remain empty.
- `CURRENCY_EXCHANGE_RATE` supplies supported FX marks with its provider timestamp and real
  bid/ask when returned. Provider-specific symbol and currency mapping stays in this package.
- HTTP-200 bodies containing `Information`, `Note` or `Error Message` become typed provider
  failures rather than quotes. Response identity, currency and venue are checked before storage.
- One persisted daily ledger guards the published 25-call/day free tier with a safe default of
  22 calls; a provider-wide minimum spacing also guards burst responses. Scheduled refresh,
  targeted manual refresh and explicit search share the same ledger.
- Alpha is not called on every typeahead keystroke. Existing normalized US-equity/ETF and FX
  identities can attach the Alpha provider explicitly; any Alpha catalog lookup is an explicit,
  budget-visible action. Equities refresh once after the US session; selected FX rows at most
  twice daily. Exhaustion is shown honestly and never bypassed by the refresh button.

**T6.2 Complete the trading and provenance contract.** Trade-action provider choices remain
derived from the shared provider catalog. The ticket compares every capable row but requires an
explicit provider choice when several exist; changing book, underlying or instrument clears or
auto-selects dependent provider/curve state according to the Phase 5 rules. UI-created opens use
`source=TRADING_TICKET`. Entry, valuation and close remain bound to the selected provider and
retain the exact normalized/raw observation or curve provenance. Prove that an open option stays
closable after its underlying leaves the watchlist; repair only if the retained active-set path
does not already do so.

Close the bounded audit/persistence items required for a defensible final project: external
fetch success/error/rate-limit metadata without response bodies; change-only quote and curve
writes; trade create/reject/close; sampled persisted valuation updates and
`VALUATION_BLOCKED`. Add the valuation write interval so SSE can remain live without unbounded
database growth. Split provider health by feed where one provider serves both fixings and curves,
and require an explicit acknowledgement for a genuinely stale curve used to open a model trade.

**T6.3 Final executable evidence and reliability pass.** Create one
`scenarios/full-provider-flow.http` covering the public routes and all seven registered sources:
Finnhub, Twelve Data and Alpha Vantage for tradeable quotes; NBP and ECB for official FX; FRED,
ECB and EIOPA for curves. Prove AAPL under three independent quote rows, EUR/USD through the
supported FX sources, and one representative trade from every supported asset class. For each
trade prove preview → server recomputation → persisted entry provenance → live revaluation →
same-source close. Recompute bond PV/par coupon, IRS legs/fair rate, option premium, currency
conversion, fair value and PnL independently.

Add a repeatable **final desk walkthrough** that builds the review state through normal APIs and
the browser, never by inserting business rows directly:

1. Start once with the retained Phase 5 database and once with a fresh disposable database.
   Create or verify named books for equity, FX, bond, IRS and option activity.
2. Search and add a recognisable instrument set: AAPL under Finnhub, Twelve Data and Alpha
   Vantage; MSFT, NVDA, JPM and KO under every selected capable intraday provider; `ASB:GPW`
   under Twelve Data as the Polish venue/currency regression; EUR/USD plus GBP/USD or USD/PLN for
   the FX path; and XAU/USD for commodity coverage. Add only providers explicitly selected by the
   user. Confirm symbol, company/name, asset class, exact venue, base/quote convention and quote
   currency before accepting the first mark. If a catalog lists an instrument that its quote
   endpoint cannot serve under the current entitlement, show and record UNSUPPORTED/NO DATA
   instead of substituting another symbol silently.
3. Verify the watchlist interaction itself: provider rows for one asset stay grouped; duplicate
   add is idempotent; manual refresh targets the chosen row and reports budget/failure honestly;
   removing one provider leaves the others; re-adding it refreshes Market Data and the New Trade
   choices; fast company switching never shows the previous row's details.
4. Open provider-bound spot trades that exercise different paths: equities through Finnhub,
   Twelve Data and Alpha Vantage EOD; EUR/USD through every capable selected FX provider; a second
   FX pair with a different quote currency; and XAU/USD through Twelve Data. Confirm the ticket's
   market/currency, side-aware executable basis, class-specific quantity unit, provider time,
   receive time and `TRADING_TICKET` provenance.
5. Build the curve-priced contracts from their inputs rather than using hidden fixtures. Use the
   minimum coverage matrix below, apply the curve-implied bond coupon/fair IRS rate where useful,
   and deliberately try one wrong-currency curve, one same-currency government curve for IRS and
   one distinct IRS projection input to prove readable rejection.

   | Category | Required review examples | What the pair proves |
   | --- | --- | --- |
   | Equity | AAPL plus another US company; `ASB:GPW` when its verified PLN feed is usable | multiple providers, BUY/SELL, US vs Polish venue/currency |
   | FX | EUR/USD plus GBP/USD or USD/PLN | base-notional/quote-currency units and two currency paths |
   | Commodity | XAU/USD; optionally XAG/USD only if the live catalog and entitlement both confirm it | quoted-unit quantity and no guessed commodity capability |
   | Bond | USD government 5Y, EUR government 10Y and a PLN risk-free example | face amount/coupon/frequency, different curves and currencies |
   | IRS | EUR receive-fixed 6M-index example and PLN pay-fixed 3M-index example | opposite directions and an explicit single-risk-free-curve approximation |
   | European option | AAPL call and another-company put; optionally a PLN-equity option only after its underlying currency is verified | call/put, strike/maturity, provider-bound underlying and same-currency discounting |

6. For **each supported category** leave at least one position open and close at least one other
   position after a valid refresh, so both unrealized and realized paths are visible. Across those
   trades, close at least one Finnhub, Twelve Data and Alpha position. Confirm every close uses the
   provider or curves frozen by the trade, writes terminal provenance once and survives a
   refresh/restart. Futures are not part of the matrix because the project has neither a futures
   quote contract nor a futures pricing model.
7. Inspect every resulting Trade Detail: terms, entry price/model value, provider or curve
   provenance, current/close value, settlement currency and realized or unrealized PnL. Compare
   each number with the corresponding provider row or an independent pricing calculation.
8. Inspect Valuations and Books: all remaining open positions are present once; status and age
   match their actual feed; gross entry value and unrealized PnL equal the visible rows; each book
   has correct open/closed counts and realized PnL; reporting-currency conversion names rate,
   provider, path and as-of. During an open US session, retain at least 20 real SPY observations
   to verify portfolio/book alpha and beta; outside it, document the honest insufficient-data or
   zero-benchmark-variance state rather than manufacturing observations.
9. Inspect Business Overview last. Its open gross entry value, unrealized PnL, realized PnL,
   total PnL, open count and closed count must reconcile exactly to Books and Valuations after FX
   conversion. Refresh and reconnect once to prove the same totals return from durable state.

Record the actual symbols, provider timestamps, trade IDs, entry/close values and independently
recomputed totals in the Phase 6 evidence. The walkthrough may leave one clearly named review
portfolio populated after acceptance; its companion cleanup removes only those scenario-owned
books/trades/watchlist memberships so repeated runs cannot accumulate ambiguous data.

Run the four bounded stress scenarios behind the provider gateway—ticket idempotency, SSE
fan-out, active-board growth and valuation soak—and record `docker stats` plus table growth.
Provider APIs themselves are never load-tested. Restart Market Data and Pricing, prove ledger
recovery, snapshot-before-SSE seeding, no economic duplicate on repeated observations, one trade
for a repeated `client_request_id`, and retained entry provenance after cleanup.

**T6.4 Whole-application browser pass.** Exercise every page and every supported action, not
only the new Alpha rows: navigation, search/add/remove/manual refresh, grouped provider rows,
quote and curve detail, every trade ticket, Trades, Valuations, Books, Business Overview,
Trade Actions, Logs and System Overview. Cover empty, single, mixed-currency, missing,
unsupported, stale, closed and rate-limited states; fast switching and reconnect; full Mac
viewport and narrow viewport; zero overlaps, unnecessary one-row horizontal scrolling, console
errors or false status/currency labels. Check all totals against their rows and observe at least
one full real refresh cycle.

As a final presentation closure, Business Overview gets one reporting-currency portfolio
summary derived from the existing durable book totals and live valuation state: **open gross
entry value, unrealized PnL, realized PnL, total PnL, open count and closed count**. Realized PnL
is cumulative profit/loss from closed trades; closed positions do not remain in open capital.
The value currently called capital is explicitly labeled gross entry value because the project
has no cash account, deposits/withdrawals or margin model, and an IRS NPV is not regulatory or
economic capital. The same aggregation helper must feed Business Overview, Books and Valuations
so their totals cannot drift.

**T6.5 Final documentation.** Add one `phase-reports/phase-6.md` that stands alone as the final
project handoff: system flow, Alpha payload normalization and budgets, complete provider/capability
matrix, trade/provenance lifecycle, audit/idempotency/restart guarantees, important financial
calculations and honest limitations. Update the README and lean references with current facts,
exact endpoints, keys, cadences and repeatable commands. Keep the optional extension backlog
below separate from shipped behavior.

**Final acceptance check.** A fresh `docker compose up --build` exposes seven registered sources
and all documented routes. The ticket compares Alpha Vantage, Finnhub and Twelve Data where they
are capable; Alpha equities are EOD, Alpha FX uses the returned basis, and no budget/error body is
mislabelled as a quote. Every supported asset can be created, priced, revalued and closed with
correct units, currency and frozen provenance; the retained review state contains both an open
and a closed example for equity, FX, commodity, bond, IRS and European option. Required audit
events, restart/idempotency proofs,
stress evidence and the whole-app browser matrix are reproducible from the repository. There is
one consistent all-books summary for open entry value and realized/unrealized/total PnL. There is
one reproducible walkthrough from provider catalog search and watchlist membership through open
and closed trades, valuation inspection and the reconciled Business Overview. There is no Phase
7 required for project completion.

**Explicitly out of scope for completion.** Alpha premium/bulk endpoints, synthetic spreads,
automatic best-price routing, historical charts/analytics, bootstrapped or licensed index
curves, volatility surfaces, futures, company fundamentals/news, order-book depth, open interest,
volume expansion, the optional trade comment, strategies, gamification, hosting and a
provider/scheduler rewrite.

### Optional extensions after final acceptance

These are product experiments, not missing requirements. Start one only when it has a visible
consumer, exact data meaning, provider entitlement and a small acceptance scenario. The most
valuable first extension is the shock and sensitivity lab below; hosting and an explainable
strategy runner remain later independent tracks. A true portfolio NAV is also separate: it
requires a cash ledger, deposits/withdrawals, fees, margin/collateral treatment and a return
methodology rather than relabeling trade entry values as cash capital.

#### Post-acceptance candidate — interactive shock and sensitivity lab

**Portfolio purpose.** Turn the existing one-position `POST /scenario` calculation into a
visual explanation of *which input moved, how the model price reacted and why*. This is a
post-acceptance extension, not a reason to expand final Phase 6. It uses the
existing pricing functions and current spot/curve snapshots; it needs no historical series
and introduces no new market-data provider.

**Two entry points, one engine.**

- **Existing position:** open the scenario tab from Trade Detail or Valuations. Contractual
  terms—bond coupon/face/maturity, IRS fixed rate/notional/direction, option strike/type and
  original maturity—remain fixed. Only hypothetical market inputs move. This answers the
  risk question: “what would this position be worth if the market changed?”
- **New trade:** after the ticket has a valid model preview, open `Explore sensitivity`.
  Market shocks can be applied to the draft, while the normal ticket fields may also be
  changed. This answers the structuring question: “how would another coupon, maturity,
  strike or direction change the price before I book anything?” The lab never submits a
  trade; execution remains an explicit return to the ticket.

**Supported one-factor controls.** Keep the first version small and interpretable:

| Asset | Existing-position market shocks | Additional pre-trade terms to explore | Expected teaching point |
| --- | --- | --- | --- |
| Equity | underlying spot % | side and quantity | price follows spot; position PnL reverses for SELL |
| FX / spot commodity | quoted spot % | side and base/quoted-unit quantity | value change is in the quote currency |
| Bond | parallel discount-curve bp shock | coupon, face value, maturity, payment frequency | yields up → PV down; maturity/coupon change sensitivity |
| IRS | parallel single-curve bp shock | fixed rate, maturity, notional, pay/receive direction | one risk-free curve implies floating cashflows and discounts both legs |
| European option | underlying spot %, assumed volatility percentage-point shock and risk-free-rate bp shock | strike, maturity, call/put and side | non-linear spot/vol response; call/put rate direction under Black–Scholes assumptions |

Volatility remains an explicit **model assumption** until a defensible market-volatility
source exists; the UI must not label it live or implied. Curve-shape scenarios, correlated
multi-factor stress and Greeks are a later increment only after the one-factor lab is clear.

**Presentation.** A compact control combines a slider, exact numeric input and reset/preset
buttons. Beside it, a one-factor sweep plots model price against the shocked input, with the
current point and selected shocked point marked. The result block shows base model price,
shocked model price, absolute/percentage price change, position value and incremental
scenario PnL in currency. Bonds and IRS additionally overlay the base and shocked curve;
options show the changed spot/vol/rate assumption. A short asset-specific explanation states
the observed direction (“rates rose 25 bp, so discounted bond cashflows are worth less”) and
names the assumptions that were held constant.

**Architecture and guardrails.** The frontend never implements pricing math. A pricing API
accepts a base draft or persisted trade plus a typed shock definition and returns base,
shocked and sweep results from the same valuation engine used by preview/live valuation.
Requests are stateless: no trade, quote, curve or valuation row is mutated. Provider, curve,
as-of and assumption provenance stay visible. Results are labeled **hypothetical model
scenario — not a forecast, market quote or executable price**. The current single-shock
endpoint remains the minimal Phase 5 evidence until this UI is deliberately scheduled.

**Acceptance examples.** From an open bond, `+25 bp` leaves coupon/face/maturity unchanged,
shows a lower shocked PV and explains the discounting effect. From a pay-fixed IRS, a parallel
single-curve shock moves both the implied floating cashflows and discounting under the documented
approximation. From a call draft, a spot or assumed-volatility sweep draws the expected
non-linear price curve while strike/maturity changes remain clearly identified as contract
edits. Closing the lab leaves trade count, stored curves, quote snapshots and valuations
unchanged. A later book-level view may aggregate the returned per-position scenario P&L, but
only after the position-level units and shock definitions are unambiguous.

---

## 7. Delivered UI reuse map *(reference, not another phase)*

This table records the design direction used across the delivered phases and the final pass. It
does not create work after Phase 6; shipped behavior remains authoritative in phase reports.

| View | Keeps | Changes |
| --- | --- | --- |
| MarketData | two-table layout, DataTable/MarketCell machinery | instruments table becomes the **watchlist board**: search+add, per-provider expandable rows (or provider columns), mid headline + basis tag, grade/age chips, CLOSED badge, UNSUPPORTED cells; **Official rates section** beside the benchmark strip (NBP/ECB fixings, as-of display, EUR/PLN cross-check chip); curve section gains **CurveChart** (multi-curve overlay) + inspector with as-of + provider |
| Trades / NewTradePanel | form flow, TERM_SCHEMAS-driven fields, validation UX | ticket v2: provider comparison row + radio, side-aware price highlight (BUY highlights ask), STALE ack, refresh button, slippage shown post-fill |
| TradeDetail (panel) | layout | + provenance block (D2/D12 fields, raw-payload drill) |
| Valuations / Blotter views | tables, filters | + provider column; valuation rows show market_data_timestamp; per-currency subtotals + reporting-currency selector with rate/path/as-of label (D28) |
| Books | cards, summary | + per-currency subtotals + converted total w/ rate as-of |
| SystemOverview / monitoring | health cards, log tail | + provider ops card (budget spent/remaining, next poll, backoff, RATE_LIMITED state); **all config controls live here** (D24) |
| BusinessOverview | as is | post-acceptance desk-home candidate — positions + watchlist movers + curve levels; no config controls on business views (D24) |
| Generator view | — | **deleted** (Phase 0) |

Design language: modern quote-board conventions — symbol + mid + Δ + age chip as the headline,
per-provider detail one expansion away, two-sided quotes shown only when real (D11), state as
form (pills/badges) not prose. Everything else stays the existing clean table language.

---

## 8. Engineering properties

The design intentionally preserves these technically important properties:

1. **Provenance drill** now lands on an exact FK (`entry_snapshot_id` → raw payload) — trade →
   quote → raw provider JSON in one join.
2. **Slippage as a first-class record** (seen vs executed, D12) — real order-flow semantics now
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
an instruments table, backtesting (the strategy milestone's opening), the replay provider (noted only).

---

## 9. Constraints retained for optional extensions

1. **Repo name** → **`trading-desk`** (D16).
2. **`MAX_ACTIVE_SYMBOLS`** → **25** to start; adding beyond the cap blocks with an
   explanation.
3. **Quote-history retention** → **90 days**, matching the shipped configuration; revisit only
   with measured database growth.
4. **Twelve Data daily ledger** → as recommended (~60% RTH / 40% off-hours).
5. **XAUUSD** → as recommended (keep if a real free key serves metals, else
   NBP-gold-reference only).
6. **BusinessOverview desk home** → yes, after v2 acceptance — with config controls kept on
   technical views only (D24).

---

## 10. Optional extension track — hosted operation, strategies and load visibility

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
(1) **Valuation write throttle ships in final Phase 6**: persist at most one valuation row per
trade per `VALUATION_WRITE_INTERVAL` (local ~1 min); the live UI is unaffected because it reads
SSE, while the database keeps a sampled history. The hosted profile may widen this to ~5 min.
The remaining items are optional hosting extensions: (2) **nightly retention sweep as a Railway
cron service** (quotes history, valuations, audit
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
comparison goes into `performance.md` (final Phase 6 stress-test numbers become this panel's
baseline). *Rejected:* psutil (dependency for what stdlib provides) and Docker-API scraping
(unavailable on Railway; self-reporting works in both worlds).

**D22 (new) — Railway topology: one public door, everything else private.**
Services: Caddy gateway (static Vite build + reverse proxy to private services + **basic-auth**),
8 backend services private-only (IPv6 mesh),
managed Postgres + volume, cron sweep service, preDeploy migration on market-data-service.
EU West region. Egress ≈ one gateway's worth; internal traffic free. The old repo stays
local-only; the fork deploys. *Rejected:* exposing each service publicly (8 auth surfaces, more
egress, contradicts the security stance taken in review).

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
