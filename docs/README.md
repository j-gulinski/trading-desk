# Documentation

Start with the current system and follow one feature end to end. Reference material and
future plans come afterwards.

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
   [provider-trading.http](../scenarios/provider-trading.http) - verify the complete feature
   and clean up test data.
7. [implementation-roadmap.md](implementation-roadmap.md) - read last; it describes future
   work, not current behavior.

## Earlier implementation background

These are useful only when tracing how the current foundation evolved:

- [implementation/foundation.md](implementation/foundation.md)
- [implementation/provider-domain.md](implementation/provider-domain.md)
- [implementation/finnhub-integration.md](implementation/finnhub-integration.md)

The feature guide is the primary explanation of current multi-provider behavior. The root
README is the operational entry point; `market-data.md` and `configuration.md` are reference
sheets rather than a second narrative.
