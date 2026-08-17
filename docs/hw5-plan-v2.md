# HW5 plan v2 — fork to a real-data trading system

> **Fresh-session brief (read this first after a context reset).** Status as of 2026-08-17:
> planning is **complete, owner-reviewed, and audited against recording 5** — nothing is
> implemented yet, no provider API keys are registered, and the new repository does not exist
> yet. **The next action is Phase 0 (§6): create the `trading-desk` repo and run the deep
> clean.** Decisions D1–D25 (§4, §11.4) are binding owner decisions — do not re-litigate them;
> the only open items are §10 #6 (a one-line teacher reconfirm at demo handover) and §11.6
> #8–11 (hosting choices, needed only when Phase 8 starts). Read alongside this file:
> `docs/hw5-plan.md` §2 (the prepared-seams table and file:line gap map of the current code —
> still accurate), `AGENTS.md` (repo conventions), and the local stack is currently RUNNING
> with 3 days of data (the 38 M-row valuations table §11.2 is live evidence — don't wipe it
> before Phase 7's log-contention audit harvests it). House rules that govern implementation:
> no code comments (self-explanatory code, rationale in `docs/`), minimal README, every config
> value gets a one-line why in `.env.example`, no unit tests — verification is scenario flows
> + the D25 load scenarios.

> **Planning artifact, v2 — for review.** Supersedes `hw5-plan.md` (kept for the record); the
> premise changed: instead of evolving `trading-microservices` in place, the project **forks to a
> new repository**, deletes every static/synthetic flow, and rebuilds market data around six real
> providers. Sources: the v1 plan, the HW5 PDF, kurs-5 expectations, the owner's directives
> (2026-08-17), a fresh repo survey, and **live API research run against all six providers on
> 2026-08-17**. Facts below are tagged *verified* (seen in a live response) or *docs* (from
> documentation — re-check at key signup).

Budget: the load-bearing anchor is the teacher's **~2-week scope** — "dobrze zaimplementować,
przetestować, zrobić jakiś stres test" [kurs-5 00:04:52]. The next-session date (possibly
Aug 31 — the transcript's own analysis flags that line as attribution-uncertain: "nie budować
na tym niczego") is *not* load-bearing; phases sum to the two-week scope regardless. Phases 0–7
= **~14–15 focused days** starting Mon Aug 17 (Phase 0's deep clean adds ~half a day) — zero
slack; Phase 6 (polish) is the designated shock absorber. **§11 adds Phase 8** (hosted showcase
on Railway + the technical load dashboard) — ~3–4 further days, targeted after the session; the
strategy runner is **deferred to HW6 proper** (owner: "for now skip generator").

---

## 1. The premise: fork, clear, rename

**Mechanics.** GitHub cannot fork a repo into the same account. The correct move:
`git clone --bare` the current repo → push to a new repository (full history preserved) → tag the
old repo's final state (`pre-fork-final`) → add a one-paragraph pointer to its README
("continued in <new-repo>") → **archive** the old repo. The old repo *is* the teacher's runnable
synthetic demo, frozen forever; the new repo owes it nothing.

**Naming — decided: `trading-desk`** (owner, 2026-08-17). It names what the system actually is
(a mini front-to-back desk: market data → ticket → blotter → books → risk) and reads
professional on a portfolio.

**What the fork buys.** The teacher's "keep the generator for the demo" advice [kurs-5 00:19:13]
is now satisfied by the *old repo*, not by a runtime flag — so the new repo can be genuinely
clean: no `SIMULATED` provider, no random flows, no dead demo machinery threaded through the
provider abstraction. This retires v1's D1 compromise entirely. **The fork approach was
acknowledged in-session** (verified verbatim, `kurs-5.txt:160-163`): to his generator advice
Jakub replied "i tak se zforkuję pewne repo i zostawię właśnie do pokazania" [~00:19:33] and
the teacher answered "Mhm, dobra, no bo później będę chciał to w jakiejś fajnej formie
graficznej" [~00:19:43] — a mid-conversation acknowledgement, not a formal sign-off, so a
one-line reconfirm when handing over the demo remains cheap insurance (§10 #6).

---

## 2. What the API research established (live probes, 2026-08-17)

### Group A — quote providers

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
and carrying demo machinery through the provider abstraction taxes a "clean project". If an
offline demo is ever needed, the honest future option is a *replay provider* that replays
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
  **projection-vs-discount selection demonstrable on the PLN swap itself**, his home ground.
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

**D7 (concretized) — Scheduler = per-provider budget governor.** Token bucket at ~80% of the
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
**Budget isolation is a rule, not an emergent property** (owner directive 2026-08-17): each
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

**D15 (new) — The curve chart stays hand-rolled SVG.** Extend the existing `Sparkline` approach
into a small `CurveChart` (tenor axis, per-curve series, as-of + provider caption) — the repo's
only viz primitive is hand-rolled inline SVG and `package.json` has zero chart dependencies;
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
manual-refresh reserve), `FINNHUB_TIER1_POLL_SECONDS=15` (60/min free tier at ~80% utilization
across a 25-symbol set), `TRADE_PRICE_TOLERANCE_PCT=1.0` (fills rejected beyond 1% of the seen
price), `IDLE_PAUSE_MINUTES=12` (inside the 10–15 min window; above Railway's 10-min sleep
threshold). `docs/configuration.md` mirrors the full table with per-profile defaults. The
counterpart rules: **code carries no comments** — it is written to be self-explanatory, with
all rationale in `docs/`; the **README shrinks to only what a stranger needs** to run and test
(the PDF's required sections, kept lean, linking into `docs/` for approaches and decisions);
and **config controls in the UI live on technical views only** (SystemOverview/monitoring),
never on business screens. One more consistency rule, straight from kurs-5 [00:32:14] ("lepiej
prosić AI o spójną strukturę kodu, niż pomieszanie dziesięciu różnych patternów"): the six
provider clients follow **one enforced module shape** — same base class, same
client/normalizer pairing, same method names — so a reviewer who has read one has read them
all.

**D25 (revised per owner, 2026-08-17) — Verification = scenario flows + scenario load tests;
no unit-test suite.** The house convention stays: `scenarios/*.http` flows verify behavior
end-to-end through the real system (rewritten for the provider world in Phase 7). The
teacher's "zaimplementować, **przetestować**, stres test" [00:04:52] is answered by **scripted
load scenarios** — small stdlib scripts (urllib + threads, no frameworks) injecting load at
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
the gateway. Every run records `docker stats` before/during/after: this *is* the teacher's
stress test, systematized. *Rejected (owner):* a unit-test suite — the scenario harness
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

Each phase ends demoable; its phase report feeds docs + finance-hub.

### Phase 0 — Fork & deep clean *(~1.5–2 days)*
Owner directive: this phase is **deep** — the fork must contain no rubbish, and simplification
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
- **Verify the preserved demo before archiving** (audit fix): fresh-clone the old repo at its
  final tag, `docker compose up --build`, click through the demo — his "fajna forma graficzna"
  [00:19:43] depends on that repo actually still booting for a stranger.

**Exit demo:** clean boot of `trading-desk` — no synthetic data anywhere, empty-but-honest UI,
health green, and a repo a reviewer can read without tripping over leftovers.

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
**Exit demo:** live AAPL on screen with honest age; a manual trade valued off Finnhub through
the (provider, symbol) cache.

### Phase 3 — Breadth, watchlist, scheduler v2 *(~2.5 days)*
Twelve Data (batch) + Alpha Vantage (EOD equities, FX bid/ask) clients/normalizers; budget
governor with daily ledgers + stagger + tiers; symbol search endpoint + watchlist CRUD;
UI: search box, add/remove, board = watchlist, capability matrix → UNSUPPORTED cells, grade
chips, CLOSED badge; provider ops card (budget gauges, next poll, backoff state).
**Exit demo:** search "NVDA", add it, watch three providers populate at their honest cadences —
Alpha Vantage's column reads "EOD (Fri)"; kill one key and the system degrades visibly.

### Phase 4 — Trading flow refactor *(~2 days)*
Ticket v2: per-provider comparison row (value, grade, age, state pill, disagreement in bps),
provider radio, STALE ack flow, targeted-refresh button. trade-action: D12 server-side
execution (freshness gate, side-aware price, tolerance, snapshot FK freeze, slippage record);
close path identical. Valuations stamped with provider; blotter/trades views gain the provider
column.
**Exit demo:** the PDF's ticket scenario end-to-end; the trade's PnL provably moves only with
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
**Exit demo:** the teacher's scenario, honestly delivered — a PLN swap prices with a *chosen*
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
**Exit demo:** click any trade → "why this price, from whom, when, what did the provider
actually send" without leaving the screen.

### Phase 7 — Hardening & documentation *(~1.5 days)*
D8 Decimal conversion + telescoping re-verification; idempotency (duplicate poll → zero
duplicate rows) + restart warm-start; **the D25 scenario load tests** (ticket storm, SSE
fan-out, active-board soak, valuation soak) with `docker stats` CPU/RSS per container
recorded into `performance.md` — the teacher's stress test, systematized; README per the PDF's
section list
(per-provider endpoint docs from §2, D11 price-basis policy, D3 STALE rationale argued from
market hours, keys how-to, run + test); scenarios refreshed (delete `full-flow.http`, add
provider/watchlist/ticket flows); decisions register updated (D1–D25); defense-prep notes:
market-index answer, log security, **write queueing including the audit he prescribed** —
scan the existing 3-day log corpus for warnings/errors evidencing write contention
[00:35:00] and record what was (or wasn't) found — and the **Decimal audit with the argued
Black–Scholes boundary**: why `erf`/`log`/`sqrt` stay float, error-magnitude vs the Decimal
quantization at the boundary, and the fact that every money leg is Decimal — the prepared
answer to "Nie korzystaliśmy z floatów" [00:52:47].

---

## 7. UI plan — reuse map

| View | Keeps | Changes |
| --- | --- | --- |
| MarketData | two-table layout, DataTable/MarketCell machinery, sparklines | instruments table becomes the **watchlist board**: search+add, per-provider expandable rows (or provider columns), mid headline + basis tag, grade/age chips, CLOSED badge, UNSUPPORTED cells; curve section gains **CurveChart** + inspector with as-of + provider |
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

## 8. Portfolio angle — v2 delta

All nine v1 ideas survive; the research strengthened these:

1. **Provenance drill** now lands on an exact FK (`entry_snapshot_id` → raw payload) — trade →
   quote → raw provider JSON in one join.
2. **Slippage as a first-class record** (seen vs executed, D12) — real order-flow semantics no
   other homework will have.
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

## 9. finance-hub

v1 §6 stands unchanged (bookkeeping now; M38/M40 per wave plan; evidence updates as phases
land; defense prep). v2 adds only:

- The §2 fact sheets are ready evidence for the market-data owner pages (provenance,
  staleness, reference-data modules) — cite the probe date.
- The 200-with-error-body pattern (AV/TD) is a concrete exhibit for the error-handling module
  (M10): status codes are not the error contract.
- Once the fork lands, update hub notes that point at `trading-microservices` paths to the new
  repo name.

---

## 10. Review outcomes (owner, 2026-08-17)

Resolved:

1. **Repo name** → **`trading-desk`** (D16).
2. **`MAX_ACTIVE_SYMBOLS`** → **25** to start; adding beyond the cap blocks with an
   explanation.
3. **Retention** → **30 days**, presented well on the dashboard; may grow later if it doesn't
   drain the volume budget.
4. **Twelve Data daily ledger** → as recommended (~60% RTH / 40% off-hours).
5. **XAUUSD** → as recommended (keep if a real free key serves metals, else
   NBP-gold-reference only).
7. **BusinessOverview desk home** → yes, as the Phase 6 stretch — with config controls kept on
   technical views only (D24).

Still open (downgraded after the recording-5 audit):

6. **Teacher one-liner** on D1 — the fork approach was **acknowledged in-session**
   (`kurs-5.txt:160-163`: Jakub's "i tak se zforkuję pewne repo i zostawię do pokazania" →
   teacher's "Mhm, dobra…"), so this is no longer a deviation pending approval, just a
   mid-conversation nod worth one reconfirming sentence when handing over the demo link.

---

## 11. Addendum (2026-08-17) — Phase 8: hosted showcase, smart trades, load dashboard

Added on the owner's directive. Grounded in three new evidence sets: a full-transcript re-scan
(kurs-1…5), live measurement of the running local stack, and Railway research **plus the actual
account state checked in the browser**.

### 11.1 Why this phase is teacher-aligned (the re-scan verdict)

This isn't garnish — the teacher has *already asked for most of it*:

- **He plans to host student demos himself, cheaply**: "postaram się znaleźć jakiś tani sposób
  uruchamiania tych aplikacji, żeby nie zbankrutować siebie i chłopaków" [kurs-4 00:31:54] —
  followed by "to musimy popracować nad optymalizacją projektów" and the striking idea:
  **"Może podam te parametry kontenera, żeby ludzie sobie ocenili jak zoptymalizowane jest te
  rozwiązania"** [00:32:24] — constrained containers as a public quality signal. A self-hosted,
  resource-capped deployment is a direct answer.
- **His stated blockers for keeping apps standing** are cost and disk-fill upkeep: "nie chcemy
  płacić za hosting tony wirtualek… i cały czas dbać o to, żeby się nie zapełniło"
  [kurs-2 01:07:54]. Auto-sleep + data ceilings remove exactly those two.
- **The technical dashboard is his personal pattern**: "ja często lubię robić metryki w takich
  dashboardach technicznych z informacją jaki jest przydzielony rozmiar bazy danych, jaki jest
  stopień wykorzystania" [kurs-1 00:08:55]; he asked the monitoring view for "ile mamy
  przydzielonego RAMu, jaki jest priorytet na procesorze" [kurs-1 00:15:29]; and his dashboard
  formula is "wizualny dashboard + szczegółowe widoki tabularyczne + enriched behavior na
  kliknięciu" [kurs-1 00:16:35]. The HW5 profiling ask [kurs-5 00:16:37/00:17:21] makes it live.
- **The horror story we already reproduced**: "niektórzy zapominają wyłączyć dokera i mają
  postgresa 50 GB zapchanego logami" [kurs-2 00:50:28]. Our own measurement (below) is that
  story in miniature — and the ceilings are the fix.
- **Smart trades = his HW6, verbatim**: "praca domowa nr 6 — proste strategie inwestycyjne…
  będziemy symulowali zawieranie transakcji w oparciu o prawdziwe dane i analizowali, jak
  zachowuje się nasz portfel" [kurs-5 00:07:01]; algorithms he named: "moving average, trend
  following" [kurs-4 00:16:17], the fair-value-vs-market divergence signal [kurs-3 00:12:42];
  benchmark question: "czy udało nam się S&P 500 pobić" [kurs-4 00:16:29]; "matematyki ciężkiej
  nie będzie" [kurs-4 00:16:41]. (Attribution corrected by the audit: his "wyłączyłbym wtedy
  ten generator" [kurs-5 00:07:17] is about the *HW6 strategies stage*, conditional — it is
  **not** a license for deleting the generator at HW5. The actual license for the fork is the
  in-session exchange at 00:19:33–43, cited in §1.)
- **Off-localhost requires access control**: "taki system musi w jakiś sposób autoryzować ten
  dostęp; lokalnie to jest trochę prostsze" [kurs-3 00:14:51] — so the hosted demo ships behind
  an auth gate from day one.

### 11.2 Measured reality (local stack, 3 days uptime, 2026-08-17)

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

### 11.3 Railway: facts and the account verdict

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

### 11.4 Decisions D17–D22

**D17 (deferred) — Smart demo trades = a thin strategy runner, not a random generator.**
*Owner (2026-08-17): "for now skip generator" — this decision is recorded as the agreed design
but its build moves to HW6 proper; only the deterministic `scenarios/demo.http` presentation
storyline stays in Phase 8.*
A new `strategy-service` (the HW6 opening) runs the teacher's own named
signals on watchlist symbols: **SMA-crossover / trend-following** on Finnhub equities, and
**fair-value-vs-market divergence** (pricing-service fair value vs market quote) where curves
price the instrument. Small fixed notional, paced within API budgets, trades into a dedicated
`STRATEGY` book, **every intent carries its signal rationale in the frozen terms** ("SMA(10/30)
crossed up @ 189.20, FINNHUB") — provenance meets strategy. Closes on opposite signal; on/off +
parameters in the UI (the familiar demo control, reborn). Alpha/beta vs SPY then answers his
literal question — "did we beat the S&P 500". *Also:* a deterministic `scenarios/demo.http`
storyline for live presentations. *Rejected:* resurrecting random flows (he himself said the
generator switches off at this stage [kurs-5 00:07:17]).

**D18 (new) — One `DEPLOY_PROFILE`, two honest modes.**
`local` (today's behavior) vs `hosted`: log level WARNING with structlog **writing JSON to
stdout** (Railway's only capture) while each service also keeps a bounded **in-memory ring of
recent log lines exposed via a `/logs/tail` endpoint — monitoring polls that instead of tailing
files**, preserving the log panel the teacher praised with the same bounded-buffer semantics;
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
projection with a warning threshold — the teacher's exact wish [kurs-1 00:08:55, 00:09:07].
(4) **Admin reset**: a token-guarded `POST /admin/reset-demo-data` truncating market history +
valuations + audit (books/trades kept; option `full=true` reseeds everything) — the user's
"reset full data" ask, safe behind auth.

**D21 (new) — The technical load dashboard.**
Each service self-reports via stdlib only (`resource.getrusage`, `os.times` deltas,
`threading.active_count`): RSS, CPU%, threads, uptime, plus domain gauges (SSE clients, queue
depth, cache sizes, budget spend, RATE_LIMITED/IDLE states). Monitoring aggregates into
`/system-load`; a new **System load** panel on SystemOverview renders it in his formula —
visual overview, tabular deep-dive, click-through to the service's logs. Local `docker stats`
comparison goes into `performance.md` (Phase 7's stress-test numbers become this panel's
baseline). *Rejected:* psutil (dependency for what stdlib provides) and Docker-API scraping
(unavailable on Railway; self-reporting works in both worlds).

**D22 (new) — Railway topology: one public door, everything else private.**
Services: Caddy gateway (static Vite build + reverse proxy to private services + **basic-auth**
— the off-localhost authorization he required), 8 backend services private-only (IPv6 mesh),
managed Postgres + volume, cron sweep service, preDeploy migration on market-data-service.
EU West region. Egress ≈ one gateway's worth; internal traffic free. The old repo stays
local-only; the fork deploys. *Rejected:* exposing each service publicly (8 auth surfaces, more
egress, contradicts his security stance).

### 11.5 Phase 8 plan (~3–4 days, after the Aug 31 session; 8.5 can land with Phase 7)

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
- ~~**8.6 Strategy runner v0**~~ — **deferred to HW6** (owner: "for now skip generator");
  D17 records the agreed design. The `scenarios/demo.http` presentation storyline stays.
- **Exit demo:** send the teacher a link. The app wakes from sleep in front of him, the load
  dashboard shows each container's RAM/CPU and the DB gauge live — and the monthly bill fits a
  hobby plan.

### 11.6 New open questions

8. **`adorable-cat`**: keep running (bill ~$8–10 with sleep) or pause/remove it (~$5–7)?
   It currently consumes the entire included credit.
9. **Timing**: host after the Aug 31 session (recommended — Phases 0–7 have zero slack), or
   pull 8.1–8.3 forward to demo a live link *at* the session?
10. **Access**: is a single shared basic-auth credential acceptable for the hosted demo
    (teacher + recruiters), or do you want per-person links?
11. **Serverless on Hobby**: if the toggle turns out to be plan-gated, accept ~$10–12/mo
    overage always-on, or fall back to manually pausing the Railway project between demos?

---

## 12. Recording-5 compliance audit (2026-08-17)

The full raw transcript (`kurs-5.txt` + `.srt`) was swept for every instruction, and the plan
adversarially cross-checked against it. Verdict: **compliant after the fixes below** — the
majority of his instructions (real-data integration, NBP among sources, domain analysis over
blind integration, UI reflection of imported data, projection/discount selection, the
currency-consistency rule, import↔create coupling, Docker-level profiling, stress test,
shared-solution consistency, HW6 deferral) were already anchored. The audit surfaced seven
findings, all now folded in:

1. **Tenor dimension on curves** (his verbatim WIBOR 3M/6M example) — was absent; now in D6
   (`index_tenor` metadata, `floating_rate_index_tenor` term, tenor guard) plus a second PLN
   curve (`PLN_NBP_BASE`) so projection-vs-discount is demonstrable on the PLN swap itself,
   with the licensed-data limitation stated instead of silently narrowed.
2. **"Przetestować" had no anchor** — D25 (as revised by the owner: no unit-test suite):
   `scenarios/*.http` flows plus four scripted scenario load tests run in Phase 7 with
   recorded `docker stats`.
3. **Generator deletion vs "dostawić nowy mikroserwis"** — resolved by the verified in-session
   exchange (§1); the plan no longer cites the HW6-stage "wyłączyłbym generator" remark as HW5
   license (§11.1 corrected).
4. **His prescribed write-contention log audit** [00:35:00] — now an explicit Phase 7 task on
   the existing 3-day log corpus.
5. **The Black–Scholes float boundary** vs "Nie korzystaliśmy z floatów" — the argued
   justification is now a scheduled defense-prep deliverable, not an implicit stance.
6. **AI-code consistency** [00:32:14] — one enforced module shape for all six provider clients
   added to D24.
7. **Aug 31 was structurally load-bearing** despite the transcript flagging that line as
   attribution-uncertain — the budget now anchors on his ~2-week scope [00:04:52], with the
   date explicitly non-load-bearing; and Phase 0 now verifies the archived demo actually boots
   from a fresh clone before archiving (his "fajna forma graficzna" depends on it).
