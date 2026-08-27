# Bounded reliability and growth checks

Current measured evidence for the local Compose stack. These checks exercise only the desk's
gateway and services; vendor APIs are never load-tested. Re-run with:

```bash
./scripts/phase6-stress.sh
```

The script requires a stored Alpha Vantage AAPL quote and an active equity book. Its only
business mutation is one idempotency-keyed one-share trade, which it closes with reason
`PHASE6_STRESS_CLEANUP`.

## Phase 6 sample — 2026-08-26

Host: Docker Desktop on macOS; retained review database; 15 symbols / 25 active/reference/
held provider rows at the read endpoint.

| Probe | Load | Result |
| --- | --- | --- |
| Ticket idempotency | 20 concurrent identical Alpha-backed opens, parallelism 10 | 20 HTTP 202 responses in 0.244 s; one unique deterministic trade ID; exactly one persisted trade, `TRADING_TICKET`, `ALPHA_VANTAGE`; scenario closed it normally |
| SSE fan-out | 20 market-data plus 20 pricing clients held for 3 s | 40 clients completed; market-data 88.15 → 89.51 MiB and 0.06% → 0.08% CPU; pricing 62.29 → 63.77 MiB and 0.01% → 0.02% CPU |
| Active-board reads | 200 `GET /market-data/quotes`, parallelism 20 | 200/200 HTTP 200 in 1.283 s (155.9 requests/s); Alpha ledger remained 2 requests / 2 credits |
| Valuation soak | natural live/restart traffic, 52 consecutive non-terminal intervals inspected | minimum durable gap 60.175 s against the 60 s setting; live SSE remains unsampled; terminal closes persist immediately |

Table counts at the fan-out/read checkpoint were 16 trades, 722 valuations, 25 current spot
rows, 99 change snapshots and 423 audits. These are a retained-state sample, not capacity
claims. The acceptance condition is bounded growth, correct idempotency and no vendor traffic
from local read/SSE fan-out—not a production throughput SLA.
