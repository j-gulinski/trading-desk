# Part 2: the desk core

Median of runs (spread = max − min). ✓ within budget, ✗ out.

## Decision

- Largest K within the market-data and pricing budgets, wsgiref: 50
- Largest K within the market-data and pricing budgets, gunicorn: 100
- Largest K within the market-data and pricing budgets, fastapi: 200
- (a) fastapi within those budgets at least one K level higher: **yes**
- (b) at K = 200, p95 at least 30 % lower beyond the larger spread: **valuation**
- Market-data + pricing CPU per client at most 10 % higher (K = 200): **yes**
- Market-data and pricing: **GO**

## Flagged runs

- none

## Tick delivery (ms, p95, budget 1000)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 47.4 (7.26) ✓ | 60.9 (11.8) ✓ | 81.0 (16.8) ✓ | 103 (36.8) ✓ |
| gunicorn | 47.5 (2.40) ✓ | 61.2 (4.99) ✓ | 74.8 (7.04) ✓ | 110 (16.5) ✓ |
| fastapi | 48.2 (4.90) ✓ | 57.3 (2.39) ✓ | 69.8 (10.3) ✓ | 84.1 (7.82) ✓ |

## Valuation freshness (ms, p95, budget 1000)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 189 (46.4) ✓ | 303 (246) ✓ | 1029 (597) ✗ | 2419 (1217) ✗ |
| gunicorn | 177 (51.4) ✓ | 368 (79.1) ✓ | 719 (501) ✓ | 1960 (920) ✗ |
| fastapi | 176 (42.8) ✓ | 300 (173) ✓ | 913 (1011) ✓ | 959 (365) ✓ |

## Price preview (ms, p95, budget 300)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 152 (51.6) ✓ | 175 (84.7) ✓ | 237 (51.3) ✓ | 467 (204) ✗ |
| gunicorn | 152 (69.7) ✓ | 205 (53.5) ✓ | 223 (72.8) ✓ | 394 (150) ✗ |
| fastapi | 183 (66.8) ✓ | 170 (27.9) ✓ | 237 (23.5) ✓ | 286 (43.6) ✓ |

## Position on screen (ms, p95, budget 3000)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 2426 (150) ✓ | 2414 (85.8) ✓ | 2482 (257) ✓ | 3077 (799) ✗ |
| gunicorn | 2408 (160) ✓ | 2419 (93.5) ✓ | 2622 (276) ✓ | 2573 (1102) ✓ |
| fastapi | 2451 (72.0) ✓ | 2387 (125) ✓ | 2465 (60.5) ✓ | 2484 (132) ✓ |

## Order execution (ms, p95, budget 500)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 119 (32.7) ✓ | 114 (12.2) ✓ | 121 (17.2) ✓ | 129 (31.8) ✓ |
| gunicorn | 125 (23.8) ✓ | 122 (11.3) ✓ | 123 (9.41) ✓ | 124 (16.1) ✓ |
| fastapi | 125 (16.8) ✓ | 131 (11.8) ✓ | 137 (18.9) ✓ | 122 (2.02) ✓ |

## Market-data and pricing errors (%, budget 1)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |
| gunicorn | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |
| fastapi | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |

## All errors (%, budget 1)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |
| gunicorn | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |
| fastapi | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ | 0.00 (0.00) ✓ |

## Market-data + pricing CPU: cores (per 100 clients)

| variant | K = 10 | K = 50 | K = 100 | K = 200 |
| --- | --- | --- | --- | --- |
| wsgiref | 0.41 (4.07) | 0.50 (1.01) | 0.70 (0.70) | 0.97 (0.48) |
| gunicorn | 0.42 (4.20) | 0.53 (1.05) | 0.66 (0.66) | 1.02 (0.51) |
| fastapi | 0.39 (3.91) | 0.43 (0.86) | 0.54 (0.54) | 0.64 (0.32) |

![p95](charts/desk_p95.png)

![cpu](charts/desk_cpu.png)
