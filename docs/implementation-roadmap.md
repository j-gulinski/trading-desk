# Implementation roadmap — real-data trading system

This roadmap records capability boundaries, dependencies, technical decisions and acceptance
checks for the real-data trading system. It is a forward-looking working plan; implemented
behavior is authoritative in the phase reports and the reference sheets (`architecture.md`,
`market-data.md`, `configuration.md`).

The migration starts from `trading-microservices`, removes synthetic/static market flows and
rebuilds market data around real providers. Provider facts come from live probes performed on
2026-08-17 or from provider documentation and are marked accordingly. Revalidate documented
limits when registering production keys.

The original core sequence was budgeted at roughly 14–15 focused engineering days. With
Phase 4 delivered (2026-08-23), the remaining sequence is roughly 5.5–6.5 focused days
(P5 ~2.5–3 · P6 ~1–1.5 · P7 ~1.5–2) — P5 re-sized 2026-08-23 when the quote-detail
enrichment and official-history backfill folded in (D35). Hosting and the technical load dashboard remain a separate capability
group. Automated strategy execution is deliberately deferred until every required v2 provider,
curve, execution and verification gate is complete.

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

1. **No free Group-A source gives equity bid/ask.** The brief's bid/ask-mapping decision is the
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
- **The tenor dimension, honestly** (audit fix — the review's driving example: a 3M vs 6M
  WIBOR projection choice on a PLN-settled swap): curve metadata gains an
  `index_tenor` label, IRS terms gain `floating_rate_index_tenor`, and validation matches the
  projection curve's declared tenor to the leg — so the *mechanism* the review described exists in
  schema, pickers, and rules. What free data cannot supply is the tenor-differentiated *curves*
  themselves (WIBOR 3M/6M are licensed; EMMI Euribor likewise) — the domain write-up states
  this trade-off explicitly instead of silently narrowing the ask.
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
this provider* — e.g. `ALPHA_VANTAGE_DAILY_BUDGET=20` (25/day free tier minus a 5-call
manual-refresh reserve), `FINNHUB_TIER1_POLL_SECONDS=15` (60/min free tier below its safe utilization
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
exercises the same logic through the real system instead. *(Owner ruling 2026-08-23:
structural/contract tests are also out — the load scripts stay because they are the
brief's stress test, and the ABC's incomplete-adapter-cannot-instantiate guarantee is
demonstrated in the Phase 6 report rather than enforced by a test.)*

**D26 (new) — Reference rows are a fourth board origin, never tradeable.** NBP/ECB fixing
pairs join the board with a `reference` origin flag (alongside watched/held/benchmark) but
never the tradeable universe: `/instruments` keeps deriving from watched ∪ held only, and
the ticket never offers a REFERENCE-grade row. Corollary pinned in code: watchlist choices
and symbol search offer **Group A only** (`shared/providers.QUOTE_PROVIDERS`, not "all
wired feeds") — otherwise `POST /watchlist {providers: ["NBP"]}` becomes legal for FX the
moment NBP registers as a wired feed. *Rejected:* reference pairs as watchlist items —
user-owned scope would mix with system-owned reference data, and removing one would
silently break currency conversion.

**D27 (new) — The reference universe is configured defaults ∪ active-trade currencies.**
Defaults: NBP `EURPLN`, `USDPLN`, gold; ECB `EURUSD`, `EURPLN`. Settlement currencies of
open trades auto-join when the source publishes them; when no official path exists the
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

**D32 (new) — `curve_type` is a small documented text vocabulary** (e.g. GOV_ZERO,
INTERBANK_REF, POLICY_PROXY) satisfying the brief's column sketch. *Rejected:*
modeling discount-vs-projection as a curve property — that is a per-trade choice and lives
in the frozen terms.

**D33 (new) — The audit matrix goes brief-literal, bounded.** Fetch success is
audited per external call with a minimal payload (provider, endpoint class, status,
duration — never bodies; ≤ ~6–8 k rows/day at cap, retention-swept); `QUOTE_WRITTEN` moves
from first-quote-only to **change-only writes** (the same discipline as history rows);
curve-set writes and `VALUATION_BLOCKED` join the matrix. *Rejected:* mapping the
brief's fetch event onto the structured log alone — defensible, but it argues with an
explicit requirement list for no real saving.

**D34 (new) — The valuation write throttle moves up from D20 into Phase 7.** At most one
persisted valuation per trade per `VALUATION_WRITE_INTERVAL_SECONDS` (local default 60 s);
SSE stays per-tick so the UI loses nothing; each persisted row is auditable. The 38 M-row /
12 GB three-day local measurement (§10.2) makes this a current-phase correctness ceiling,
not hosting polish. *Rejected:* leaving it hosted-only — the local database provably blows
up within days, and a review window can span days.

**D35 (new) — Free-tier surface is mined before it is expanded.** Two principles decided
2026-08-23 after auditing what the wired responses already contain. (1) **Fields already
paid for ship first**: day range (both quote providers), 52-week range and volume
(Twelve Data — documented; Alpha Vantage EOD volume verified, joins in Phase 6) enter the
normalized quote as nullable stored-as-received extras and surface in the Quote Detail
session block, with an honest n/a where a tier does not publish — zero additional
requests, and the review's volume question becomes a shipped feature instead of a
deferred one. Order-book depth and open interest remain genuinely unpublished on the free
tiers and stay out. (2) **Every further capability passes the runbook §6 five-answers
bar** (exact measure, instrument scope, interval/as-of, units, entitlement) before any
field or endpoint is added: company profile/fundamentals (Finnhub, budget-priced),
provider candles/`time_series` (would reopen the intraday-chart decision as a labeled
per-provider capability), and company news are recorded on the post-acceptance list under
exactly that gate. *Rejected:* adding capabilities because an endpoint exists — budget
spend and false-completeness are the two ways a free-tier desk starts lying.

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
  Phase 7 load scripts stay — they are the brief's stress test.
- **The demo's live bugs become Phase 4 inputs (B1–B5)**, folded into Phase 4 below with
  their code-level hypotheses.
- **A standing phase template** now governs phases 4–7 so every phase is one complete,
  reviewable step.

### The standing phase template (phases 4–7)

1. **Verify** — re-run the previous phase's gate on a fresh stack before building.
2. **Build** — backend, then surface (UI), then ops/audit visibility.
3. **Evidence** — a phase scenario `.http` flow plus a retained evidence record in the
   phase-3b format (commit, market session, IDs, both clocks, probes).
4. **Browser pass, driven by a real scenario** — every touched view exercised in the
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
5. **Docs & report, after implementation, in the same change** — the
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

### Phase 5 — FRED + ECB yield curves, curve plotting, curve-driven pricing, quote-detail enrichment *(~2.5–3 days)*

**Goal.** Real rate curves with per-point provenance in the schema, the brief's
`/curves*` routes live, **curves drawn as a real, comparative chart** (the plot is a
deliverable, not a garnish), and curve-priced classes pricing from selectable,
currency-consistent, tenor-labeled curves — the review's projection-vs-discount ask made
concrete on screen. Decisions: D31–D32 (+ D6, D15).

**Verify *(0.25 d)*:** Phase-4 gate green on a fresh stack (reference rows, resolver,
conversion labels).

**T5.1 Migration *(0.25 d)*.** `market_data_curves` gains `raw_payload JSONB` (one fetch =
one raw source response per set — the brief's reproducibility requirement, currently
missing from the schema) and `curve_type` (D32 vocabulary); the spot board gains D35's
nullable session columns (day open/high/low, 52-week bounds, volume, average volume) —
change-only snapshots stay untouched; up/down clean on a fresh DB — the phase-1 gauntlet
re-run.

**T5.2 Clients + assembly *(~0.75 d)*.** `clients/fred.py` (JSON; values are strings,
`"."` = missing; the 120/min key budget fits the shared bucket shape) and ECB yield curves
via the csvdata path. Builders on the `shared/curves.py` contracts: `USD_TREASURY`
(11 DGS series), `EUR_GOV_AAA` + `EUR_GOV_ALL` (a real projection-vs-discount choice),
`PLN_REF` composite (two live OECD anchors, monthly, ~2-month lag, **linear**
interpolation, per-point `source_series`/`source_as_of`, NULL series = derived point),
`PLN_NBP_BASE` (flat at the configured NBP reference rate, labeled a proxy). Calendar
windows: FRED ~16:15 ET daily, OECD weekly, ECB YC ~12:00 CET.

**T5.3 Routes + stream.** `GET /curves`, `GET /curves/<provider>`,
`POST /curves/refresh`, curve sets in `/market-data/snapshot` (the placeholder finally
filled), a `curve_update` SSE event on the existing contract; curve-set writes audited
(D33).

**T5.4 CurveChart + pickers *(~0.75 d)*.** Hand-rolled SVG (D15, zero chart
dependencies), built to be *used*: tenor axis in years with labeled tenors, rate axis,
**multi-curve overlay** (any sets side by side — EUR AAA vs ALL; PLN composite vs NBP
base; USD Treasury), a legend naming provider + as-of per curve, hover on a point opens
the **inspector** (tenor, rate, source series, source as-of, ingest time, raw-response
drill), derived/interpolated points visually distinct from real anchors. `TERM_SCHEMAS`
gain `settlement_currency`, `discount_curve`, `projection_curve`,
`floating_rate_index_tenor`; currency and tenor guards reject incompatible choices with a
readable reason ("PLN swap cannot discount on USD_TREASURY"); pricing swaps `USD_GOV` for
the live curve registry; curve-priced classes unblock at the ticket for currencies with a
wired curve, and the ticket's curve pickers show currency + tenor + as-of so the choice is
informed. The PLN proxy/composite limitations stay explicit rather than being presented as
observed WIBOR curves.

**T5.5 Quote-detail enrichment + official history backfill *(~0.5 d, D35)*.** Two
additions that cost no new provider requests, converting the review's volume question
into a shipped, honest feature:

- **Session fields the quote responses already carry and the normalizer discards.**
  Finnhub `/quote` publishes `o/h/l`; Twelve Data's quote publishes `open/high/low`,
  `fifty_two_week` and — per its documentation — `volume` + `average_volume` for
  supported instruments (verify live with the registered key; the probes verified Alpha
  Vantage's EOD volume, which slots into the same fields in Phase 6). Ingest them as
  **nullable, stored-as-received** extras on the normalized quote and the board row
  (columns ride T5.1's migration; change-only snapshots stay price-provenance and are
  untouched); the wire tick carries them; the **Quote Detail panel gains a session
  block** — day range, 52-week range where published, volume where published, each
  provider-labeled, honest "n/a" where the free tier does not publish (Finnhub volume —
  the UNSUPPORTED lesson again, one level down). The board table itself does not change.
  Each field enters through the runbook §6 five-answers bar: measure (session cumulative
  share volume / prior-close volume for EOD grade), instrument scope, interval/as-of,
  units, entitlement.
- **Official-fixing history backfill.** NBP serves dated fixing ranges (93-day window
  cap) and gold history; ECB EXR serves `lastNObservations=N`. On feed boot, when a
  reference pair's stored history is sparse, backfill up to `REFERENCE_BACKFILL_DAYS`
  (default 90, matching retention) as ordinary change-only snapshots — each with its own
  as-of `provider_timestamp`, the backfill moment as `received_at` (the two-clock
  contract stays honest: "when the market said it" vs "when we ingested it"), and the
  range-response slice as raw. The reference drill then shows weeks of daily fixings
  instead of "first observed value", and — unlike the sparse quote tapes — a fixing
  series is *complete by construction* (one value per business day), which the guide
  should note as the reason the tape reads as a real series here.

**T5.6 Evidence + browser pass + docs *(~0.5 d)*.** `scenarios/curves.http` (the
brief's curl forms) + evidence record. Browser pass: the curve section and chart
interactions (overlay toggling, inspector, derived-point styling), ticket curve pickers
and rejection copy, Trades/Valuations for a curve-priced trade, the FRED ops card, the
enriched Quote Detail session block on all three row kinds (Finnhub, Twelve Data,
reference). Docs per the standing template, including the PLN investigation narrative
(NBP has no rates API — 404 verified; WIBOR licensed; what the monthly lag costs) as the
domain-analysis centerpiece, and the **brief-to-source mapping** the review clarified:
the brief's NBP row ("kursy walutowe i dane referencyjne dla krzywych") maps to FX
fixings + the reference-point set + the config-sourced `PLN_NBP_BASE` rate, while the
term structures come from ECB (EUR) and FRED (USD, PLN anchors) — stated against the
brief's own detailed bullets so the reasoning is on paper before anyone asks. Candidate
diagrams: the curve assembly pipeline (series → points → set → chart → pricing), the
curves/points ER with the new raw/type columns, an annotated sketch of the interpolation
between the two PLN anchors, and the chart's own screenshot as evidence.

**Acceptance check:** a USD instrument prices from `USD_TREASURY`; EUR AAA vs ALL is
selectable and **visually comparable on one chart**; a PLN swap chooses a PLN construct
and rejects `USD_TREASURY` with the reason; the inspector traces every plotted point to
provider, series, source date, ingest time and raw response; interpolated points are
visually distinct; `/curves*` and curve SSE work via the brief's curls; the Quote Detail
session block shows day range on both quote providers, 52-week and volume on Twelve Data
rows, and an honest n/a for Finnhub volume; a reference drill shows a multi-week fixing
tape with per-row as-of dates and backfill-time receive stamps; migration up/down clean;
browser pass clean.

**Out of scope:** bootstrapping/splines, curve-versioning UI, vol surfaces, chart
libraries, licensed WIBOR/Euribor data (documented, not silently narrowed), order-book
depth and open interest (still unpublished on the free tiers — the volume answer does
not reopen them), candles/intraday charts (post-acceptance, D35's gate).

### Phase 6 — Alpha Vantage and the complete three-source ticket *(~1–1.5 days)*

**Goal.** The third quote provider closes the brief's comparison view; the provider
transport boundary goes formally abstract exactly when it earns its keep (the third
adapter); the ticket gains its last two required fields.

**Verify *(0.25 d)*:** Phase-5 gate green (curves price, chart draws, guards reject).

**T6.1 Client + feed *(~0.5 d)*.** `clients/alpha_vantage.py`: body-aware
`"Information"` / `"Note"` / `"Error Message"` classification (errors hide in 200s);
`GLOBAL_QUOTE` equities as **EOD grade** (date-only timestamp → the UI renders
"EOD (Aug 21)", never fake-LIVE); `CURRENCY_EXCHANGE_RATE` FX with real bid/ask + full
datetime — the one free true-spread feed, so basis `BID_ASK` finally appears live.
`alpha_vantage_feed.py`: 25/day ledger with a 5-call manual-refresh reserve (budget 20),
fixed slots — equities once after US close, the FX anchor 2×/day; search joins the merged
discovery path.

**T6.2 ABC + registry-driven choices *(~0.25 d)*.** `ProviderClient` becomes an ABC:
`provider`/`base_url` abstract and `classify_body` an `@abstractmethod` — every adapter
must state its body-error rule even when it is "none", and an incomplete adapter is
uninstantiable (the demoable `TypeError`, shown in the phase report per the D25 ruling —
no test enforces it). Feeds stay **composed**, not inherited: cadence, budget and calendar
policies differ materially, now proven across three unlike providers. Trade-action
provider options go registry-driven with the per-symbol capability cache resolved at
watchlist-add (closing the open item in `market-data.md`); the ticket adds the **optional
comment** (persisted into the frozen terms) and the explicit **`TRADING_TICKET` source**.

**T6.3 Evidence + browser pass + docs *(~0.5 d)*.** The provider scenario extended to
three sources + evidence record. Browser pass: the ticket with three provider rows (grades
honest, N/A where unsupported, comment field UX), the board's AV rows reading
"EOD (date)", the AV ops card (25/day gauge + reserve), Trades/Valuations showing comment
and source. Docs per the standing template; candidate diagrams: the client class hierarchy
(ABC → three quote clients + two official clients, hooks marked), the three-provider
ticket sequence (compare → choose → server-price → freeze), the AV daily-budget timeline
(slots + reserve). The report also carries the honest typing answer (a `TypeVar` bound
informs the checker; the runtime contract here is ABC) and the MRO paragraph.

**Acceptance check:** AAPL displays three independent provider rows, with Alpha Vantage
reading `EOD (date)` rather than LIVE; EURUSD exposes real Alpha Vantage bid/ask while
equities stay LAST; a trade opened on Alpha Vantage persists its comment and
`TRADING_TICKET` source and moves only when that provider's quote changes; instantiating a
deliberately incomplete client raises `TypeError` (demonstrated in the report);
**extensibility probe: adding a seventh provider = one client + one feed + one registry
line, nothing else edited** — stated in the report as the shared-feed readiness note
(a future external shared feed plugs in as exactly this); browser pass clean.

**Out of scope:** AV premium endpoints, bulk anything, spread synthesis for last-only
feeds, an inheritance tree over the feeds, any test harness.

### Phase 7 — brief compliance, provenance and hardening *(~1.5–2 days)*

**Goal.** Close every remaining compliance gap, prove the system honest under load and
restart, and bring the README + reference sheets to the full brief contract so a stranger
can run, verify and grade the system from the repository alone. The load scripts are the brief's
required stress test, not a test suite (D25 + owner ruling). Decisions: D33–D34.

**Verify *(0.25 d)*:** Phase-6 gate green; six providers on `/providers`.

**T7.1 Provenance closure *(0.25 d)*.** The exact normalized and raw observation used by
entry/close stays immutable and reachable (FK sweep-skips re-proved); official curve rows
retain raw payloads (T5.1); the valuation-stream fields checked one-for-one against the
brief's example event. No transient log file is the only evidence for anything.

**T7.2 Audit matrix *(0.5 d, D33 + D34)*.** The brief's ten events with bounded
payloads: fetch success per call (minimal payload — provider, endpoint class, status,
duration; never bodies; retention-swept), fetch error / rate limit (existing transitions +
severity review), `QUOTE_WRITTEN` on change-only writes (replacing first-quote-only —
README's noise rationale updates in the same change), curve-set writes (from P5), trade
create/reject/close (existing), persisted valuation updates, and `VALUATION_BLOCKED` for
the frozen-provider-missing case. D34 lands here: at most one persisted valuation per trade
per `VALUATION_WRITE_INTERVAL_SECONDS` (local 60 s; SSE stays per-tick), which is what
makes the valuation event auditable without row explosion — and removes the measured
38 M-row local failure mode.

**T7.3 Idempotency & restart proofs *(0.25 d)*.** Duplicate provider observations add no
economic duplicate; a repeated `client_request_id` stays one trade; provider
ledgers/cooldowns recover across restart; snapshots seed consumers before SSE follow-up;
referenced provenance survives a forced retention sweep.

**T7.4 Six-provider scenario + stress test *(~0.5 d)*.** The final
`scenarios/full-provider-flow.http` — the brief's curl list runs verbatim — then the
four D25 loads (`load_ticket_storm`, `load_sse_fanout`, `load_active_board`,
`load_valuation_soak`) with `docker stats` before/during/after and database growth vs the
D20 ceilings recorded in `docs/performance.md`. Full-system browser pass: every view
touched this cycle plus a whole-app UX sweep (navigation, empty states, error copy,
side-panel stacking), zero console errors, screenshots retained.

**T7.5 README + reference sheets to the full contract *(~0.5 d)*.** Every brief-required README section
present (architecture, services, all six integrations with the endpoints used, keys
how-to, schema, normalization, curve construction, ticket, realized/unrealized PnL,
compose run, test commands, known limitations) as lean prose linking into docs/ (D24),
plus the **deviation table**: `ENABLE_RANDOM_MARKET_DATA_FALLBACK` intentionally absent
(the fork removed the generator, D1 — the archived repo is the fallback), the brief's
generic poll-interval names mapped to the actual per-provider knobs, and the spot-board
raw-via-snapshot-FK note. Final checks re-run: Decimal boundary, lint, build, dead-code,
`git diff --check`, fresh `docker compose up --build` acceptance with a retained evidence
record. Phase report teaches: the idempotency proofs step by step, monotonic vs wall
clocks, queue/thread behavior under the load scripts; candidate diagrams: the audit-event
map (which service writes which of the ten events, where) and the load-test topology
(where each script injects, what it measures).

**Final acceptance check:** one fresh `docker compose up --build` exposes all six
providers; the brief's curl routes succeed as written; the ticket compares Alpha
Vantage, Finnhub and Twelve Data; entry, live PnL and close use one frozen source;
NBP/ECB/FRED reference data drives the documented, plotted curves; every required audit
event is observable; the full scenario and stress-test report are repeatable from the
repository alone; browser pass clean across the application.

Not on the v2 critical path: a connected intraday chart and provider candles
(`time_series`), order-book depth and open interest (unpublished on the free tiers —
published volume itself ships in Phase 5, D35), company profile/fundamentals and company
news (each gated by the runbook §6 five-answers bar, D35), best-quote routing,
BusinessOverview expansion, gamification, strategies, hosting and a broad
provider/scheduler rewrite. They begin only after the final acceptance check. (The
gamification hook needs nothing beyond Phase 6's extensibility probe — a shared external
feed will be one more client + feed + registry line.)

---

## 7. UI plan — reuse map

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

## 9. Locked implementation decisions

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
