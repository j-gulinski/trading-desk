# Multi-provider market data and trading

This guide explains how Finnhub and Twelve Data move through the application: symbol
search, provider-specific watchlist membership, polling, the quote board, trade entry,
valuation, close and provider logs. It describes the current code and the reasons for the
few rules that cross service boundaries.

For exact environment defaults use [configuration.md](../configuration.md). For field and
provider reference use [market-data.md](../market-data.md). For hands-on verification use
[validation-runbook.md](../validation-runbook.md).

## Scope and guarantees

The implemented feature guarantees that:

- a symbol can be watched on Finnhub, Twelve Data or both;
- every quote remains identified by `(provider, symbol)`;
- the ticket compares the providers that are actually watching the selected symbol;
- the server chooses the execution price from the selected provider's current quote;
- the trade stores provider, provider timestamp and snapshot provenance;
- valuation and close continue to use the provider stored on the trade;
- upstream calls are visible in the existing structured Logs flow.

The feature does not fetch vendor backfill, add smart routing, ingest official rate curves
or implement exchange order queuing. A trade here is portfolio booking against a usable
quote, not an exchange order.

## The whole system in one diagram

```mermaid
flowchart LR
    F[Finnhub API] --> C[Provider clients]
    T[Twelve Data API] --> C
    C --> N[Quote normalizer]
    N --> P[(spot board + snapshots)]
    N --> S[market_tick SSE]
    P --> A[Market Data REST API]
    A --> U[React market board and ticket]
    S --> U
    S --> R[Pricing quote cache]
    U --> X[Trade Action Service]
    X --> D[(Trades)]
    D --> R
    R --> V[(Valuations)]
    R --> B[valuation SSE]
    B --> U
    C --> L[structured provider_http_response log]
    L --> M[Monitoring log tail]
    M --> U
```

There are two important ownership rules:

1. Only Market Data Service connects to vendors. Other services consume normalized rows or
   the normalized SSE stream.
2. SSE distributes changes, but PostgreSQL remains the source of truth. Consumers seed or
   reconcile after startup because SSE has no replay.

## Code map

Read one vertical flow instead of reading directories alphabetically.

| Concern | Main files |
| --- | --- |
| Provider facts and normalized quote | `shared/providers.py`, `shared/quotes.py`, `shared/freshness.py` |
| Active provider-symbol set | `shared/active_set.py`, `services/market-data-service/app/watchlist.py` |
| Vendor HTTP | `clients/base.py`, `clients/finnhub.py`, `clients/twelve_data.py` |
| Vendor payload mapping | `services/market-data-service/app/normalizer.py` |
| Polling and budgets | `finnhub_feed.py`, `twelve_data_feed.py`, `provider_runtime.py`, `budget.py` |
| Board, snapshot and Today series | `persistence.py`, `publisher.py`, `api.py` |
| Market UI | `useMarketFeed.js`, `useWatchlist.js`, `MarketData.jsx` |
| Ticket comparison | `domain/tradeActions.js`, `NewTradePanel.jsx`, `ProviderQuoteOption.jsx` |
| Server execution | `trade-action-service/app/trade_processor.py`, `market_state.py`, `repository.py` |
| Provider-bound valuation | `pricing-service/app/cache.py`, `valuation_engine.py` |
| Provider log inspection | `clients/base.py`, `monitoring-service`, `Logs.jsx` |

## Flow 1: search and watch one provider

```mermaid
sequenceDiagram
    participant UI as WatchlistSearch
    participant API as Market Data API
    participant FH as Finnhub feed
    participant TD as Twelve Data feed
    participant DB as PostgreSQL

    UI->>API: GET /symbols/search?q=AAPL
    par budgeted provider searches
        API->>FH: search AAPL
        API->>TD: search AAPL
    end
    API-->>UI: normalized results with capable providers
    UI->>API: POST /watchlist providers=[FINNHUB]
    API->>DB: insert/merge provider membership
    API->>FH: reload active set
    API->>TD: reload active set
    API-->>UI: current provider membership
```

`watchlist_items` has one row per symbol and a JSON object containing only the chosen
providers. Capabilities are derived from `shared/providers.py`; they are not stored as user
choices. Adding Twelve Data later merges it into the same symbol row. Removing
`?provider=TWELVE_DATA` leaves Finnhub untouched.

The active set combines three reasons to keep polling:

- `watched_by`: explicitly selected on the watchlist;
- `held_by`: required by an active trade, using only that trade's frozen provider;
- `benchmark_by`: required for book risk.

This is why removing a watchlist provider may remove the board row immediately or may return
it in `still_polled`: an open position still needs it.

## Flow 2: vendor quote to board and consumers

```mermaid
sequenceDiagram
    participant Feed as Provider feed
    participant Client as ProviderClient
    participant Norm as normalizer.py
    participant DB as PostgreSQL
    participant SSE as publisher.py
    participant UI as React
    participant Pricing as Pricing Service

    Feed->>Client: budgeted REST request
    Client-->>Feed: vendor JSON
    Feed->>Norm: provider payload + symbol metadata
    Norm-->>Feed: NormalizedQuote
    Feed->>DB: upsert latest board row
    alt price changed
        Feed->>DB: append snapshot with raw payload
    end
    Feed->>SSE: publish market_tick
    SSE-->>UI: update provider-symbol row
    SSE-->>Pricing: update provider-symbol cache
```

The normalized shape keeps vendor-specific parsing at the edge. `bid`, `ask` and `last` are
never invented. `mid` is derived once: bid/ask midpoint when both exist, otherwise the
official reference value, otherwise last. `price_basis` records that choice.

The current board and the snapshot table answer different questions:

- `market_data_spot_prices`: what is the latest accepted quote for this provider-symbol?
- `market_data_snapshots`: which price changes and raw provider payloads did we observe?

The board is overwritten on every successful poll. A snapshot is appended only when a price
field changes. This avoids turning unchanged closed-market confirmation polls into thousands
of history rows.

Network failures are returned to the budget-aware feed loop; the HTTP client does not make a
hidden second attempt. This keeps the token bucket, daily-credit ledger and upstream calls in
agreement.

### Today change and Today trend

Both UI fields now use the same provider baseline:

- start: the provider's `previous_close`;
- end: the latest normalized `mid`;
- middle: actual price changes stored since UTC midnight, reduced to the last observation in
  each five-minute bucket.

`persistence.today_history_series()` uses normal SQLAlchemy queries and small Python grouping;
there is no PostgreSQL-specific `DISTINCT ON`/`unnest` query. It always includes the current
board value. This means a closed market still shows the previous-session move instead of a
flat browser-only line.

The middle of the line contains only quotes this application collected. It does not pretend
to be vendor-backfilled intraday history from before the service started.

## Flow 3: selected provider to trade, valuation and close

```mermaid
sequenceDiagram
    participant UI as NewTradePanel
    participant Action as Trade Action Service
    participant DB as PostgreSQL
    participant Pricing as Pricing Service
    participant Blotter as Blotter Service

    UI->>Action: POST /trade-actions with provider + client_seen_price
    Action->>DB: read active book, membership and current provider quote
    Action->>Action: validate and choose ask/bid/mid
    Action-->>UI: 202 accepted or 422 reason
    Action->>DB: validate again and insert trade
    DB-->>Pricing: active-trade reconciliation
    Pricing->>Pricing: read cache[(provider, symbol)]
    Pricing->>DB: insert valuation
    Pricing-->>Blotter: valuation_update SSE
    Note over Action,Pricing: Close uses the same stored provider with the side reversed
```

The browser sends `client_seen_price`, not an execution price. The server reads the newest
board row and chooses:

- BUY: ask, falling back to normalized mid when the feed has no spread;
- SELL: bid, with the same fallback;
- CLOSE: the opposite side on the provider stored on the trade.

If the quote moved more than `TRADE_PRICE_TOLERANCE_PCT` from what the user saw, the request
is rejected. Validation runs once before the `202` response and again in the worker because
the market can move while the intent is queued.

The insert records `market_data_provider`, executed `trade_price`, `client_seen_price`,
`entry_price_timestamp`, optional `entry_snapshot_id` and `created_by_service`. Close records
the matching price timestamp and optional snapshot ID. A snapshot ID is present only when
the exact current board observation created a change-history row; unchanged confirmation
polls never reuse an older ID. The browser cannot choose any persisted provenance field.

Pricing caches quotes by `(provider, symbol)`. `value_trade()` first resolves the provider
on the trade and then reads only that cache key. A newer quote from another provider cannot
reprice the position. The same provider is included in the valuation payload and blotter
response so the choice remains visible end to end.

## Market state and closed-market booking

The state model separates session state from data failure:

| State | Meaning | New trade |
| --- | --- | --- |
| LIVE | Provider timestamp is inside the open-market freshness budget | allowed |
| CLOSED | Venue is closed and confirmation polls still arrive | allowed |
| STALE | Expected provider updates are no longer arriving | blocked |
| MISSING | Provider should serve the row but has no quote | blocked |
| UNSUPPORTED | Provider does not serve this asset class | not offered |

`CLOSED` is bookable because this application records portfolio transactions; it does not
queue exchange orders. The stored quote state, provider timestamp and snapshot make that
choice explicit. A future order-management feature would replace this rule with venue-hours
execution.

## Flow 4: provider calls to Logs

```mermaid
flowchart LR
    A[ProviderClient.get] --> B[one provider_http_response event]
    B --> C[service JSON log file]
    C --> D[Monitoring tail worker]
    D --> E[log seed + SSE]
    E --> F[Logs filters: service, provider, Provider API]
```

`ProviderClient` logs once after each completed response or error. The entry includes the
provider, public endpoint, safe symbol/search context, HTTP status, duration, result count and
outcome. Authentication parameters are added only when constructing the URL and are never
included in log fields.

Provider cards link to the existing Logs view with filters in the hash URL. No second log
store was added; provider inspection reuses the central log reader and SSE flow already
present in the application.

## Provider pacing and failure isolation

Finnhub and Twelve Data share the client error types, token bucket, runtime health model,
normalizer contract, persistence and publisher. Their feed loops remain separate because
their actual constraints differ:

| Provider | Polling shape | Binding budget |
| --- | --- | --- |
| Finnhub | one symbol per request; faster tier for held symbols and benchmark; slower watchlist tier; closed cadence | requests per minute |
| Twelve Data | multi-symbol quote request; one credit per symbol; flat cadence adjusted to active symbol count | minute burst plus daily credits |

An upstream failure changes only that provider runtime:

- 401/403: `AUTH_FAILED` cooldown;
- 429: `RATE_LIMITED`, honoring `Retry-After` when present;
- network/5xx: short `ERROR` backoff;
- one bad symbol in a Twelve Data batch: warning for that symbol while valid batch rows continue.

Provider health is returned by `/providers` and `/providers/<name>/health`. The UI renders
configured feeds with cadence, market session, last success and budgets. Unwired future
providers render only `NOT AVAILABLE`.

## Public boundaries

| Endpoint | Purpose |
| --- | --- |
| `GET /symbols/search?q=` | normalized, provider-tagged discovery |
| `GET/POST /watchlist` | list or merge provider membership |
| `DELETE /watchlist/<symbol>?provider=` | remove one provider membership |
| `GET /quotes` and `/quotes/<provider>/<symbol>` | current normalized board |
| `GET /history` | previous-close-anchored Today series |
| `GET /snapshot` + `GET /stream` | seed and live normalized quote updates |
| `GET /providers` + `/providers/<name>/health` | provider runtime and budgets |
| `POST /refresh?symbol=&provider=` | immediate budgeted poll |
| `GET /instruments` | tradeable symbols and their provider choices |
| `POST /trade-actions` | provider-bound open/close intent |

The service also accepts the assignment-style `/market-data/...` aliases. The frontend uses
`/api/market-data/...`; Vite removes the `/api/market-data` prefix before proxying to the
service-root routes.

## Data model additions

The migration adds only state needed by these flows:

- watchlist provider choices;
- board freshness/session fields, previous close and latest snapshot reference;
- trade provider, server execution provenance and the price seen by the client;
- valuation provider and market timestamp.

The foreign key from a trade to its entry snapshot has no cascade. Retention skips snapshots
referenced by trades and the current board, so audit provenance cannot be removed by cleanup.

## Verification route

Run [provider-trading.http](../../scenarios/provider-trading.http) and verify in the browser:

1. Search AAPL and add Finnhub only, then Twelve Data.
2. Confirm two independent board rows and remove only one provider.
3. Confirm Change today and Trend today start at the same previous close and end at the same
   current mid, including when the venue is closed.
4. Open the ticket, compare provider rows and submit one usable LIVE or CLOSED quote.
5. Confirm Trades shows the chosen provider, quote time and server execution price.
6. Confirm valuation and close retain that provider.
7. Open a provider card and confirm Logs is filtered to completed upstream calls without API
   keys.
8. Exercise STALE, missing and moved-price rejection paths and confirm the user receives the
   exact reason.

See [validation-runbook.md](../validation-runbook.md) for cleanup and expected UI states.
