# Part 2: core flows

**Stub alone** at 1 250 calls at once: 6 150 calls/s, p50 202 ms, p99 225 ms

**Revaluation** (Black–Scholes, `desk_pricing`, 3 runs): 0.83 µs per position (0.82–1.02) = 0.014 cores for 1 000 000 positions per minute

## Market data in

Median of runs (min–max).

| variant | refresh every T s | quote age p95, s | refreshes on time % | errors % | CPU cores | CPU ms per refresh | runs | within budget |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gunicorn | 10 | 9.51 (9.51–9.51) | 100 (100–100) | 0 (0–0) | 0.32 (0.31–0.32) | 0.32 (0.31–0.32) | 3 | yes |
| gunicorn | 5 | 4.76 (4.76–4.76) | 100 (100–100) | 0 (0–0) | 0.32 (0.31–0.34) | 0.16 (0.16–0.17) | 3 | yes |
| gunicorn | 2 | 1.93 (1.91–2.04) | 100 (100–100) | 0 (0–0) | 0.61 (0.55–0.65) | 0.12 (0.11–0.13) | 3 | yes |
| fastapi | 10 | 9.51 (9.51–9.51) | 100 (100–100) | 0 (0–0) | 0.19 (0.19–0.19) | 0.19 (0.19–0.19) | 3 | yes |
| fastapi | 5 | 4.76 (4.76–4.77) | 100 (100–100) | 0 (0–0) | 0.22 (0.2–0.22) | 0.11 (0.098–0.11) | 3 | yes |
| fastapi | 2 | 1.96 (1.96–2.02) | 100 (99.2–100) | 0 (0–0) | 0.36 (0.32–0.43) | 0.072 (0.065–0.086) | 3 | yes |

## Order entry

Median of runs (min–max).

| variant | orders at once | p95, ms | errors % | CPU cores | CPU ms per order | runs | within budget |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gunicorn | 10 | 5.75 (4.02–6.09) | 0 (0–0) | 0.99 (0.99–0.99) | 0.4 (0.29–0.41) | 3 | yes |
| gunicorn | 50 | 85.0 (77.5–89.5) | 0 (0–0) | 0.99 (0.99–0.99) | 0.38 (0.36–0.41) | 3 | yes |
| gunicorn | 200 | 147 (98.2–158) | 0 (0–0) | 0.99 (0.99–1) | 0.4 (0.27–0.43) | 3 | yes |
| fastapi | 10 | 5.62 (3.82–6.32) | 0 (0–0) | 0.99 (0.99–1) | 0.48 (0.35–0.5) | 3 | yes |
| fastapi | 50 | 96.8 (85.4–103) | 0 (0–0) | 1 (0.99–1) | 0.54 (0.49–0.57) | 3 | yes |
| fastapi | 200 | 617 (360–705) | 0 (0–0) | 0.99 (0.99–1) | 0.54 (0.34–0.64) | 3 | **no** |

## Valuation stream

Median of runs (min–max).

| variant | subscribers | delivery p95, ms | errors % | CPU cores | CPU ms per update | runs | within budget |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gunicorn | 50 | 3.39 (3.34–3.47) | 0 (0–0) | 0.12 (0.11–0.12) | 0.047 (0.046–0.047) | 3 | yes |
| gunicorn | 200 | 6.52 (5.93–6.69) | 0 (0–0) | 0.26 (0.24–0.27) | 0.026 (0.024–0.027) | 3 | yes |
| gunicorn | 500 | 7.88 (7.58–7.89) | 0 (0–0) | 0.38 (0.38–0.39) | 0.015 (0.015–0.015) | 3 | yes |
| fastapi | 50 | 3.47 (3.45–3.87) | 0 (0–0) | 0.069 (0.068–0.07) | 0.028 (0.027–0.028) | 3 | yes |
| fastapi | 200 | 6.74 (6.37–6.77) | 0 (0–0) | 0.13 (0.13–0.14) | 0.013 (0.013–0.014) | 3 | yes |
| fastapi | 500 | 8.38 (7.07–9.72) | 0 (0–0) | 0.17 (0.17–0.22) | 0.0068 (0.0068–0.0088) | 3 | yes |

## Provider client libraries

One run per point, 10 s; the stub answers in 200 ms.

| client | model | in flight | calls/s | CPU ms per call | errors |
| --- | --- | --- | --- | --- | --- |
| httpx | threads | 400 | 133 | 10.527 | 0 |
| httpx | threads | 1000 | 159 | 9.731 | 0 |
| requests | threads | 400 | 1960 | 0.326 | 0 |
| requests | threads | 1000 | 3528 | 0.335 | 0 |
| urllib3 | threads | 400 | 1960 | 0.212 | 0 |
| urllib3 | threads | 1000 | 4934 | 0.17 | 0 |
| httpx | async | 400 | 124 | 9.98 | 0 |
| httpx | async | 1000 | 240 | 8.178 | 2 |
| aiohttp | async | 400 | 1932 | 0.088 | 0 |
| aiohttp | async | 1000 | 4872 | 0.056 | 0 |

## Rule at target level

| Flow | gunicorn within budget | FastAPI within budget | FastAPI CPU per operation vs gunicorn | Decision |
| --- | --- | --- | --- | --- |
| Market data in | yes | yes | -33 % | GO: FastAPI uses less CPU per operation |
| Order entry | yes | yes | +41 % | NO-GO |
| Valuation stream | yes | yes | -50 % | GO: FastAPI uses less CPU per operation |
