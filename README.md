# trading-desk

A mini front-to-back trading desk: market data → trade ticket → blotter → books → risk.
Six Python microservices (bottle, SQLAlchemy, structlog) plus Postgres and a React/Vite
frontend, communicating through database rows and server-sent events.

Forked from [trading-microservices](https://github.com/j-gulinski/trading-microservices),
which stays archived as the runnable synthetic demo. This repository removes every synthetic
flow and rebuilds market data around six real providers — Finnhub, Twelve Data, Alpha Vantage
(quotes), NBP, ECB, FRED (official rates and curves) — landing phase by phase per
[docs/hw5-plan-v2.md](docs/hw5-plan-v2.md). Current state: the deep clean is done; the market
data board is honestly empty until the first provider client lands.

## Running

```
cp .env.example .env      # set a real POSTGRES_PASSWORD (and mirror it in both DATABASE_* URLs)
docker compose up --build
open http://localhost:3000
```

Provider API keys go into `.env` as they are registered — signup links: [finnhub.io](https://finnhub.io),
[twelvedata.com](https://twelvedata.com/register), [alphavantage.co](https://www.alphavantage.co/support/#api-key),
[fred.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). NBP and ECB need no key.

The browser talks only to the Vite dev server; every `/api/<service>/…` call is proxied to the
matching container (`frontend/vite.config.js`). Every configuration knob is listed in
`.env.example`; each one's rationale is in [docs/configuration.md](docs/configuration.md).

## Services

| Service | Port | Owns |
| --- | --- | --- |
| market-data-service | 8001 | provider quotes and curves, snapshot + SSE stream |
| pricing-service | 8002 | valuations, PnL, book alpha/beta, valuation SSE |
| monitoring-service | 8003 | health polling, audit trail queries, central log tail |
| books-service | 8004 | trading books CRUD |
| blotter-service | 8006 | trade and valuation read models |
| trade-action-service | 8008 | the only writer of trades; intent queue |

Each service builds its own image from the shared `docker/service.Dockerfile` template
(python:3.14-slim, multi-stage, one dependency layer from the root `requirements.txt`) and
boots through `shared/service_runtime.py`.

## Testing

No unit-test suite by design: behavior is verified end-to-end through the HTTP flows in
`scenarios/*.http` (any REST-client runner), and from Phase 7 on through scripted load
scenarios whose measured results land in `docs/performance.md`.

## Where to read more

[docs/README.md](docs/README.md) is the index: the base architecture, the configuration
reference, the plan of record (`docs/hw5-plan-v2.md`), and per-phase reports. Documentation is
produced phase by phase — each phase ships the docs for what it built.
