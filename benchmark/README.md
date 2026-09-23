# Benchmark: Bottle (WSGI) vs FastAPI (ASGI)

Stage 1 of the migration assignment. The same small app is built twice — `sample_wsgi/`
(Bottle) and `sample_asgi/` (FastAPI) — with the same four endpoints. Only the HTTP layer
differs. Criteria are in `../docs/decision_criteria.md`, interpretation in `../docs/report.md`.

| Scenario | Endpoint | What it isolates |
| --- | --- | --- |
| S1 | `GET /health` | framework and server overhead |
| S2 | `GET /io` | waiting 50 ms on another service (`downstream_stub/`) |
| S3 | `GET /cpu` | computation: 20 000 rounds of SHA-256 |
| S4 | `GET /books` | the real books-service code: one query, 20 books |

| Variant | Command |
| --- | --- |
| A | `gunicorn -w 1 sample_wsgi.app:app` (sync worker) |
| A-threads | `gunicorn -w 1 --threads 40 sample_wsgi.app:app` (gthread worker) |
| B | `uvicorn sample_asgi.app:app --workers 1 --no-access-log` |

## Running it

```sh
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r benchmark/requirements.txt
# hey: brew install hey, or go install github.com/rakyll/hey@latest
docker compose up -d postgres db-migrations          # or any migrated database
export DATABASE_URL=postgresql+psycopg://trading:<password>@localhost:5432/trading_desk
benchmark/run_benchmark.sh                          # about 1 h 45 min
python benchmark/analyze.py                         # tables, charts, gate check
```

The script seeds 20 books if they are missing, starts the stub and all three variants,
checks that the stub keeps up at c = 200 (`results/stub_c200.txt`), then runs the grid:
3 runs × 4 scenarios × c = 1, 10, 50, 200 × 3 variants. The variants alternate at every
point. Each point is 10 s of warm-up (discarded) and 30 s of measurement with `hey -t 10`.
`DURATION`, `WARMUP`, `RUNS` and `N` can be overridden from the environment.

Output, one file per measurement:

- `results/<variant>_<scenario>_c<c>_run<n>.txt` — hey summary: throughput, percentiles,
  status codes, errors;
- `results/….usage.csv` — CPU % and RSS of the server process, one sample per second;
- `results/summary.md`, `results/summary.csv`, `charts/s1–s4.png` — from `analyze.py`.

## Decisions that differ from the PDF's example

- **One worker process (N = 1), not four.** Every service runs as one process today, and
  five of the six cannot run more copies (report, 2.1). There was also a technical reason,
  found in the smoke test: with `--workers` above 1, uvicorn 0.53 binds its socket without
  the TCP protocol number, so asyncio never sets `TCP_NODELAY` on accepted connections. Every
  keep-alive request then waits for a delayed ACK: `/health` at c = 1 took p95 0.3 ms with one
  worker and 44 ms with two. `gunicorn -k uvicorn.workers.UvicornWorker` does not have the
  problem.
- **One stub process, not two**, for the same reason: B calls the stub through a keep-alive
  `httpx.AsyncClient`, and a two-worker stub added about 40 ms to every call.
- **The server is pinned to core 0** (`taskset`). The load generator, stub, monitor and the
  database share the other cores. macOS has no `taskset`, so there the processes are not
  pinned and the client and server compete for cores.

## Measured on

| | |
| --- | --- |
| Machine | cloud VM, Intel Xeon @ 2.10 GHz, 4 vCPU, 15 GB RAM |
| System | Ubuntu 24.04.4, Linux 6.18 |
| Python | 3.14.7 |
| Database | PostgreSQL 16.13 on the same VM, pinned to cores 2–3 (the project uses 18.6) |
| Load generator | hey 0.1.5 |
| Libraries | `requirements.txt` |
