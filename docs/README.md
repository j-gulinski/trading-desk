# Documentation

Organized by **topic** rather than by the order things were built. Each document opens with its
subject in a handful of steps, then explains each step: what was needed, what was chosen, what
was rejected, and what the code actually does.

## Reading order

**The system**

| # | Document | Read it for |
| --- | --- | --- |
| 1 | [architecture.md](architecture.md) | The whole system in one pass: who owns what, the three rules, one trade end to end, the data model |
| 2 | [pricing.md](pricing.md) | How instruments are defined and priced: frozen terms, discount factors, Black–Scholes, IRS, scenarios |
| 3 | [alpha-beta.md](alpha-beta.md) | What the ALPHA/BETA cards mean and how they are computed, with a worked example |
| 4 | [logging.md](logging.md) | How a log line travels from a service to a live screen, and the two observability trails |
| 5 | [performance.md](performance.md) | What was measured, what is bounded, and what breaks first under load |
| 6 | [decisions.md](decisions.md) | Every fork, what was rejected, and why — the fastest way back into context |

**The frontend** — the bulk of this project, so it has its own set in
[`frontend/`](frontend/README.md):

| # | Document | Read it for |
| --- | --- | --- |
| F0 | [frontend/README.md](frontend/README.md) | Stack, folder structure, the ten patterns, and the recipe for adding a view |
| F1 | [frontend/react.md](frontend/react.md) | The React model itself — rendering, state, effects, refs, keys, context — for a backend developer |
| F2 | [frontend/data.md](frontend/data.md) | The HTTP boundary, polling, SSE, snapshot+stream reconciliation, the render throttle |
| F3 | [frontend/screens.md](frontend/screens.md) | The domain layer, tables, filters, forms and writes, panels, UI states |
| F4 | [frontend/styling.md](frontend/styling.md) | SCSS architecture, tokens, layout mechanics, container queries, accessibility |

`designs/` holds the wireframes each screen was built from. The root
[`README.md`](../README.md) is the operational entry point: how to run the system, what each
screen shows, and the submission-level summary.

**If you are returning to this project after a break,** read `decisions.md` first — it is the
index of intent — then whichever topic you are about to touch.

## The system in one paragraph

Seven Python services (market data, pricing, books, blotter, trade generation, trade action,
monitoring) share one Postgres and communicate through database rows rather than calls. Market
data invents prices; pricing revalues affected trades on every tick and publishes valuations and
per-book alpha/beta over SSE; trade-action is the only writer of trades and accepts intents on a
queue; monitoring polls health and tails every service's log file into memory. A React frontend
merges snapshot and stream into nine views. Everything runs with `docker compose up --build`;
the UI is at `http://localhost:3000`.

## Known limitations, consolidated

The honest list. Each one is a decision with a reason, not an oversight — the details are in the
linked document.

**Pricing** ([pricing.md](pricing.md#9-current-limits))
- Options use a fixed house-default volatility; no vol feed, no implied vol, no Greeks, and no
  repricing from the passage of time alone.
- One published curve serves both discounting and projection.
- A custom-defined instrument exists only in its own trade's frozen terms — there is no shared
  `instruments` catalog to publish it to.
- Trade entry prices come from the simulator.

**Risk** ([alpha-beta.md](alpha-beta.md#10-known-limitations))
- The benchmark is built from the books' own instruments, so betas measure real co-movement but
  are partly self-referential until real market data replaces the feed.
- Engine state is in memory: a pricing restart re-enters warm-up.
- Exposure is regression-estimated at face PnL; hedge-aware netting is future work.

**Logging** ([logging.md](logging.md#12-deliberately-not-built))
- Buffers are per-process and bounded: no long-term retention, no cross-restart search beyond
  the 64 KB warm-start tail, and a second monitoring replica would hold a disjoint view.
- Lines written between the last scan and a file rotation are lost.
- Line ids order by *collection* time, not by the lines' own timestamps, so services interleave
  slightly out of order within a one-second window.

**Frontend** ([frontend/README.md](frontend/README.md#7-what-the-frontend-deliberately-does-not-do))
- Tables render a bounded window; full history needs server-side pagination.
- Three simultaneous tabs can exhaust the HTTP/1.1 per-origin connection budget.
- SSE gives eventual state, not an auditable event tape.
- Entity links from log lines land on a view, not a specific row.

**Trade and book lifecycle** ([frontend/screens.md](frontend/screens.md#5-writes--validate-submit-observe))
- Closing is one-way and one-shape: no reopen, no price override, and a fixed `MANUAL_CLOSE`
  reason.
- `CLOSE_ALL` is deliberately not in the UI, and it is not simply the bulk version of a single
  close: it never writes `close_price`, so realized PnL for a bulk-closed trade is not
  reconstructable the way a normal close is. Its audit rows also carry no `correlation_id`
  ([logging.md §9](logging.md#9-step-7--the-story-panels-two-ways-to-ask-a-question)).
- A deactivated book cannot be reactivated from the UI, and deletion is one book at a time.
- The book summary computes positions for every book on every poll, including collapsed cards —
  bounded by the book count, so it has never been worth deferring.
- Generator settings live in process memory: a restart returns to the environment defaults
  ([architecture.md §7](architecture.md#7-patterns-inside-a-service)).

**System** ([architecture.md](architecture.md))
- Propagation between services is bounded by polling intervals (~2 s for pricing, 5 s for the
  blotter), not instantaneous.
- No authentication, authorization, or multi-user isolation — explicitly out of scope at this
  stage.

## What comes next

The next phase replaces the synthetic generator with real market data (Alpha Vantage / Finnhub /
Twelve Data for quotes, NBP / ECB / FRED for curves), making market-data-service the only
external gateway.

**One question ranked most of the decisions in `decisions.md`: does this survive the switch to
real data unchanged?** It is what kept the cov/var estimator, the tick-and-curve SSE contract, and
the JSONB frozen terms — and what replaced the closed-form IRS float leg and the scenario engine's
duplicated pricing, both of which worked fine against a simulator. The corollary is the harder
half: **existing code has no tenure.** "It works today" was never the argument; "it works
identically on real data" was. What that phase confirms about the current design:

- **Nothing about the listed-vs-OTC split moves.** Group A providers quote exactly the listed
  catalog classes; Group B feeds the curves that price OTC products and bonds.
- **The `market_inputs` / `price_from_inputs` seam absorbs it.** Provider selection is a
  market-inputs concern (which quote to read); the pricing math is untouched.
- **The freeze-at-open pattern extends directly** — `market_data_provider`,
  `reference_price_timestamp` and `snapshot_id` join the terms already frozen in `metadata`.
- **The alpha/beta estimator does not change.** It samples whenever the benchmark updates, so a
  real index series just means a slower cadence and a longer window.
- **The logging stack absorbs provider failures as routine lines** — fetch failures and
  rate-limit hits land in `market-data-service.log` and are one level-filter click away.
- **The random generator survives as the sanctioned fallback.**

The one structural change it forces: provider becomes a key dimension. The pricing cache and the
market stream are keyed by symbol today; they will need `(provider, symbol)`.

## Keeping these documents true

- **A document is updated in the same change as the code it describes.** These are not release
  notes; they always describe the system as it is now.
- **Rationale lives here, constraints live in the code.** A comment states something the code
  cannot show (an invariant, a bound); the *why* belongs in a document. Prose duplicated in both
  places drifts apart, and the drift is invisible until it misleads.
- **When a decision is reversed, update the row in `decisions.md`** rather than appending a new
  one — the register is the current state of intent, and git holds the history.
- **New limitations go in two places:** the owning document's limits section, and the
  consolidated list above.
