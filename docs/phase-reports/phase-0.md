# Phase 0 — fork & deep clean

Phase 0's job was to make the fork *real*: `trading-desk` had to stop being a renamed copy of
the synthetic demo and become a clean starting point for the provider build — no random flows,
no seeded prices, no dead machinery. The owner's directive made it a **deep** clean:
simplification by extraction in scope, not just deletion. Fork mechanics (bare-clone push,
`pre-fork-final` tag, README pointer, archive, fresh-clone demo verification) were completed
2026-08-17; this report covers the surgery. **Exit criterion, met:** clean boot, no synthetic
data anywhere, empty-but-honest UI, health green.

Two standing decisions recorded here:

- **Phase reports live in `docs/phase-reports/`.** Docs are produced per phase; the per-phase
  narrative is the one genuinely chronological artifact.
- **Report format:** worth-knowing bullets — each one a decision, change, or implementation
  with its why, extended in place (mechanism, evidence, convention, honest limits) only where
  the topic is hard.

## Step 1 — clear the synthetic flows

**Needed:** everything that invented data had to go — the trade-generation service (random
open/close engine), the market-data simulator (random-walk threads plus hardcoded
ACME/XAUUSD/ES_FUT/EURUSD/MARKET_INDEX seeds and the USD_GOV curve anchor), the Generator UI,
and the synthetic MARKET_INDEX benchmark wiring.

- **Deleted by inventory:** the whole trade-generation service (its compose block, env knobs,
  and monitoring target included), `market-data-service/app/generator.py` plus the persistence
  seeds, the Generator view/route/icon/proxy/endpoints/styles, `MarketIndexCard` and every
  `MARKET_INDEX` fallback, and `scenarios/full-flow.http`. Compose lands at eight containers
  plus the frontend.
- **Two deliberate saves.** The Trade Actions view *survives* but consumed two generator-named
  modules — `IntentFeed` moved to `components/tradeactions/` and its row helpers into
  `domain/tradeActions.js`, both stripped of generated-vs-manual discrimination (no `gen-`
  correlation ids exist anymore). And `INSTRUMENT_CATALOG` stays: trade-action validation,
  term schemas, and the ticket depend on it — Phase 1 *replaces* it with the symbol master
  rather than Phase 0 deleting it.
- **A default that would now lie, fixed.** An intent arriving without `source` was recorded as
  `GENERATED`; with the generator gone, every UI-opened trade would have been mislabeled — the
  default is now `MANUAL`.
- **Empty is served honestly.** `/snapshot` returns `{spots: {}, curves: {}}`, and
  market-data's rich health payload (simulator tick counters) collapsed into the runtime's
  standard one.

## Step 2 — extract the service bootstrap

**Needed:** six `main.py` files carried the same copy-pasted threaded-server adapter and boot
litany, with three ad-hoc variations: blotter blocks on a DB warm-start *before* serving,
pricing starts two background threads, monitoring hid its startup inside the server adapter's
`run()` override.

- **One runtime, an API shaped by the observed needs:**
  `run_service(name, app, port, startup=(), background=())`. Startup hooks run to completion
  before anything else — blotter still loads its trades before serving; each background
  callable gets its own daemon thread; the server is *exactly* the one every service already
  ran (a threaded WSGI server on `0.0.0.0` and the declared port), now defined once.
- **A default `/health` only where none exists.** Services with a three-line
  `{service, status: UP}` handler dropped it; pricing and blotter keep their richer payloads.
- **Deliberately left out (owner direction during review): hosting portability.** The IPv6
  dual-stack bind Railway's private network would need and the `PORT`/`BIND_HOST` environment
  contract. No future-phase enablement lives in the code — that work ships with Phase 8, and
  the research stays recorded in the plan (§8.1, §11.3).
- **Result — a `main.py` is now a declaration of what the service is.** Blotter's, complete:

  ```python
  from app.api import app
  from app.config import PORT, SERVICE_NAME
  from app.loader import bootstrap_trades
  from app.pricing_service_client import valuation_stream_consumer
  from shared.service_runtime import run_service

  if __name__ == "__main__":
      run_service(SERVICE_NAME, app, PORT, startup=[bootstrap_trades], background=[valuation_stream_consumer])
  ```

  The per-service `HOST` constant is gone — binding is runtime policy, not service code.

## Step 3 — unify configuration access

**Needed:** three coexisting config patterns (shared module constants, per-service re-exports,
raw `os.environ` reads in pricing) — plus a booby trap: `shared/config.py` did
`int(os.environ.get("TICK_INTERVAL_MS"))` with no default, so *every* service, books included,
refused to boot unless the simulator knobs were set.

- **One rule.** `os.environ` is read only inside `shared/config.py`, through typed helpers
  (`env_str` / `env_int` / `env_float` / `env_required`). A missing required variable now
  fails at boot *with its name*, not with an anonymous `int(None)` TypeError.
- **Knobs live with their consumer.** Only genuinely cross-service values stay shared
  (`DATABASE_URL`, `LOG_*`); the stream URLs moved to pricing and blotter, the blotter URL to
  books, the healthcheck map to monitoring, the risk knobs to pricing — ending pricing's
  third pattern.
- **Dead weight out.** Ten orphaned variables deleted (the simulator/generator knobs among
  them), dead `LOG_LEVEL` imports swept, and `shared/enums.py` cut to the one enum any code
  consumes (`Severity`).

## Step 4 — one Dockerfile template, still one image per service

**Needed:** seven near-identical single-stage `python:3.14` Dockerfiles at **1.69 GB each**,
with `pip install` *after* the source copy (every source edit re-installed dependencies), no
`.dockerignore` (each build shipped the whole repo — docs, frontend, `.git` — to the daemon),
and a separate `Dockerfile.migrate`.

- **What this does *not* change: the microservice split.** Each of the six services still
  builds its **own image** and runs as its **own container and process** — compose starts
  eight containers exactly as before, and `docker exec <svc> cat /proc/1/cmdline` shows each
  running its own `python -m app.main` on its own copy of its own code. What was seven copies
  of the same build *recipe* is now one parameterized file that `docker build` runs once per
  service. (`shared/service_runtime.py` is the same idea at the code level: a library each
  process imports, not a shared process.) The architecture decision — independent services
  communicating through database rows and SSE, each restartable on its own — stands untouched.
- **The template, verbatim** (one root `requirements.txt` replaces the per-service copies,
  which were already identical modulo alembic):

  ```dockerfile
  FROM python:3.14-slim AS deps
  COPY requirements.txt /tmp/requirements.txt
  RUN python -m venv /opt/venv \
   && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

  FROM python:3.14-slim
  ARG SERVICE_DIR
  ENV PATH="/opt/venv/bin:$PATH"
  WORKDIR /app
  COPY --from=deps /opt/venv /opt/venv
  COPY alembic.ini ./
  COPY shared/ shared/
  COPY db/ db/
  COPY ${SERVICE_DIR}/ ./
  CMD ["python", "-m", "app.main"]
  ```

- **Two stages instead of one.** Stage 1 (`deps`) exists only to produce the `/opt/venv`
  folder; stage 2 starts from a clean slim base and copies that finished folder in. Whatever
  stage 1 needed to work (the copied requirements file, pip's machinery) never enters the
  final image.
- **The venv is not for isolation — it is the one-folder trick.** A bare `pip install`
  scatters output across the system Python (packages into `…/site-packages/`, entry-point
  executables like `alembic` into `/usr/local/bin/`); `python -m venv /opt/venv` gathers
  packages *and* executables under one directory, so a single `COPY --from=deps` moves the
  complete dependency set — Python's `node_modules`, effectively. `/opt` is the Linux
  convention for self-contained add-on software, leaving the image three clean territories:
  `/usr/local` (the base image's Python), `/opt/venv` (our dependencies), `/app` (our code).
- **Why `/opt/venv/bin/pip` by full path.** After `venv` runs there are *two* pips on disk,
  and each installs into the environment it belongs to (`pip --version` literally names it) —
  the path chooses where packages land. Bare `pip` would be the system one, and the venv we
  copy forward would ship empty.
- **Why `--no-cache-dir`.** Pip keeps downloaded wheels in `~/.cache/pip` to speed up *future*
  installs; in an image build pip runs exactly once, so the cache would be write-only bytes
  in the build layer. (In this multi-stage shape it never reaches the final image anyway —
  the flag trims the intermediate layer and is standard hygiene.)
- **`ENV PATH="/opt/venv/bin:$PATH"` is the whole of "activation".** `python` now resolves to
  the venv's interpreter and `alembic` resolves for the migrations container — `source
  activate` does essentially nothing more than this PATH edit.
- **The step order is the cache fix.** Docker reuses a step's cached result until one of its
  inputs changes. The deps stage depends only on `requirements.txt`, and source is copied in
  stage 2 *after* the venv — so editing code never re-runs pip (the old files had it
  backwards). And because stage 1 is byte-identical for every service, Docker builds it once
  and all seven images share the result.
- **`ARG SERVICE_DIR` is the only per-service input**; `python -m app.main` from
  `WORKDIR /app` keeps the working directory on Python's import path, so `app` and `shared`
  import exactly as before.
- **`psycopg` became `psycopg[binary]`.** The slim image ships without libpq (Postgres's C
  client library); the `[binary]` wheel bundles its own copy, so nothing needs apt.
- **One flagged addition beyond the plan's "slim images" bullet:** every image copies
  `alembic.ini` + `db/` (a few KB), so *any* service image can run migrations —
  `Dockerfile.migrate` is deleted and the db-migrations compose entry reuses the market-data
  image for its one-shot `alembic upgrade head` job container, which exits before the
  services start.
- **Result (measured): 1.69 GB → 299 MB** per Python service on arm64 (~5.6×). The slim base
  and the venv are byte-identical *layers* across the seven images — Docker stores an
  identical layer once, so total unique backend image content is ~300 MB, not 7 × 299 (a
  storage effect; running containers stay fully separate). Full 8-image rebuild: ~13 s warm.
  Root and frontend `.dockerignore` files keep build contexts small; `.gitignore` gained
  `/tmp/` and `*.py[cod]`. The frontend image stays a Vite dev server (the HMR workflow)
  until Phase 8.2.

## Step 5 — env & docs reset

**Needed:** D24 — a knob without a written *why* doesn't exist — and documentation that
describes this system, not the forked one. Both bullets below were shaped by owner direction
during review.

- **`.env.example` is lean:** variables plus one pointer comment; every knob's rationale lives
  in `docs/configuration.md`. It lists the four provider key placeholders (Finnhub, Twelve
  Data, Alpha Vantage, FRED — NBP and ECB need none), `BENCHMARK_SYMBOL=SPY` (sampling stays
  inert until the Finnhub feed lands), and the pricing risk knobs. `POSTGRES_DB` renamed to
  `trading_desk`.
- **Docs cleared to a starter set, produced per phase from here.** The pre-fork topic docs,
  the `designs/` wireframes, and the superseded v1 plan are deleted — they documented the
  archived system and live on in the archived repo. What remains describes the base: a
  concise `docs/architecture.md`, `docs/configuration.md`, the plan of record, and
  `docs/phase-reports/`. Each phase ships the documentation for what it built, in the same
  change.
- **`README.md` reset to the minimal runbook** (what the system is, fork context, run steps,
  key signup links, service table, testing policy, docs index). The PDF-mandated sections
  (per-provider endpoints, price basis, freshness) land in Phase 7 when they describe running
  code. `AGENTS.md` aligned with the unified image/runtime/docs reality.

## Step 6 — verification

- **Static:** `py_compile` clean across `services/ shared/ db/`; oxlint clean; **knip clean** —
  the sweep also caught six unused exports (three pre-existing, three orphaned by the
  MarketIndexCard deletion), all internalized; `vite build` passes.
- **Boot:** fresh volume, full migration chain applied by the unified image (exit 0); all six
  services healthy plus postgres — monitoring shows **7/7 UP** with no trade-generation
  target; `/snapshot` returns `{spots: {}, curves: {}}`.
- **One real fix surfaced by the empty world — and it teaches how WSGI streams.** A WSGI
  server sends the HTTP status line and headers *lazily*, together with the first bytes of the
  response body. Market-data's SSE route returns a generator that blocks on `queue.get()`
  until an event exists — so with no ticks ever, nothing was yielded, no headers went out, and
  the HTTP response never started. Both kinds of client wait on headers before declaring a
  connection open: pricing's `urllib.request.urlopen` blocks inside the call, and the
  browser's `EventSource` stays in CONNECTING — so both sat there forever. The simulator's
  instant first tick had masked this for the whole life of the old repo. The fix is the SSE
  idiom pricing's valuation stream already used: yield a `: connected` line immediately on
  attach — lines starting with `:` are SSE *comments*, which clients must ignore, making them
  the standard way to force headers out (and, later, to keep idle connections alive). With the
  two SSE routes now the same shape, the UI honestly shows **2/2 streams connected · "No
  instruments published yet."**
- **UI (Playwright):** every view renders with zero console errors; no Generator in the nav;
  Trade Actions works through the relocated feed; the page title finally says *Trading Desk*.

## Carried forward, deliberately

- `INSTRUMENT_CATALOG` still lists the synthetic symbols — the ticket can open trades against
  them but nothing values them (no prices exist). Phase 1's symbol master replaces it.
- `market_data_spot_prices.source` keeps its `'SIMULATED'` server default — schema is Phase 1
  migration territory.
- Alpha/beta sampling is inert until SPY ticks arrive (Phase 2+); the cards read
  INSUFFICIENT_DATA, which is the honest state.
- Pricing's `market_data_connection` flips CONNECTED on stream attach now, but
  `received_events` stays 0 until Phase 2 — also honest.

## Still open (user actions)

- **Register the four API keys** (finnhub.io, twelvedata.com, alphavantage.co,
  fred.stlouisfed.org) into `.env` — blocks Phase 2 and the metals check.
- **Metals check** (Phase 0 item, key-gated): one Twelve Data + one Alpha Vantage XAU/USD probe
  with real keys decides whether XAUUSD stays a tradeable symbol or NBP gold remains the only
  metals reference (review outcome #5).
