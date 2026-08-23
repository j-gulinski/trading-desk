# Documentation

Start with the current system and follow one feature end to end. Reference material comes
next; the plan of record comes last — unless you are here to build the next phase, in which
case jump straight to it.

**Working on the next phase?** Read [`../AGENTS.md`](../AGENTS.md) for the house rules,
then [implementation-roadmap.md](implementation-roadmap.md) §6: the standing phase
template (verify → build → surface → evidence → browser pass → docs) and the task-level
plans for phases 4–7 (decisions D26–D34) are there. Each phase ends by adding its report
to `phase-reports/` and updating the guides in the same change.

## Reading order

1. [Root README](../README.md) - run the stack, see the services and learn the operating
   rules.
2. [architecture.md](architecture.md) - understand service ownership, database handoffs and
   SSE boundaries.
3. [implementation/multi-provider-trading.md](implementation/multi-provider-trading.md) -
   follow the implemented search -> watchlist -> quote -> ticket -> valuation -> logs flow,
   including code maps and diagrams.
4. [market-data.md](market-data.md) - look up normalized fields, provider facts, endpoints
   and persistence contracts.
5. [configuration.md](configuration.md) - look up each runtime knob, default and rationale.
6. [validation-runbook.md](validation-runbook.md) and
   [provider-trading.http](../scenarios/provider-trading.http) - review the complete feature
   with Observe → Explain → Probe prompts, retain a compact evidence record and clean up test
   data.
7. [phase-reports/](phase-reports/) - the chronological record, one report per phase:
   [phase-0](phase-reports/phase-0.md) (fork & deep clean),
   [phase-1](phase-reports/phase-1.md) (contracts & schema),
   [phase-2](phase-reports/phase-2.md) (Finnhub vertical),
   [phase-3a](phase-reports/phase-3a.md) (two-provider workflow review record),
   [phase-3b](phase-reports/phase-3b.md) (review closure — the latest concrete evidence and
   the exact boundary handed to Phase 4).
8. [implementation-roadmap.md](implementation-roadmap.md) - the plan of record: decisions
   D1–D34, the standing phase template, task-level phases 4–7, and the post-acceptance hosted
   sequence. Forward-looking by design; implemented behavior is authoritative in the guides
   above.

## Earlier implementation background

These are useful only when tracing how the current foundation evolved:

- [implementation/foundation.md](implementation/foundation.md)
- [implementation/provider-domain.md](implementation/provider-domain.md)
- [implementation/finnhub-integration.md](implementation/finnhub-integration.md)

The feature guide is the primary explanation of current multi-provider behavior. The root
README is the operational entry point; `market-data.md` and `configuration.md` are reference
sheets rather than a second narrative.
