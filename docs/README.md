# Documentation

Cleared to a starter set at the fork (Phase 0) and **produced phase by phase from here**: each
phase ships the documentation for what it built, in the same change — a document describes the
system as it is now, or it does not exist. The pre-fork docs live in the archived
[trading-microservices](https://github.com/j-gulinski/trading-microservices) repo.

| Document | Read it for |
| --- | --- |
| [architecture.md](architecture.md) | The base system: services, the three rules, data model, runtime shape |
| [configuration.md](configuration.md) | Every environment knob — default, consumer, rationale |
| [market-data.md](market-data.md) | The six providers (probed facts), quote/curve/freshness contracts, market store |
| [hw5-plan-v2.md](hw5-plan-v2.md) | The plan of record: providers, decisions D1–D25, phases |
| [phase-reports/](phase-reports/) | One report per phase — what was needed, what was chosen, what landed |

Further documents appear as their phases land; [hw5-plan-v2.md](hw5-plan-v2.md) says what
and when.

The root [README.md](../README.md) is the operational entry point: what the system is and how
to run and test it.
