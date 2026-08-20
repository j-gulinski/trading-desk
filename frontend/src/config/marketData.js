export const STREAM_EVENTS = ['market_tick', 'market_remove']

export const WATCHLIST_POLL_INTERVAL_MS = 10000

export const SYMBOL_SEARCH_DEBOUNCE_MS = 400

export const SYMBOL_SEARCH_MIN_CHARS = 2

export const SYMBOL_SEARCH_SHOWN_LIMIT = 8

export const PROVIDERS_POLL_INTERVAL_MS = 5000

export const FRESHNESS_PILL_LEVELS = {
  LIVE: 'info',
  STALE: 'stale',
  CLOSED: 'closed',
  MISSING: 'degraded',
  UNSUPPORTED: 'unknown',
}

export const FRESHNESS_LABELS = {
  LIVE: 'LIVE',
  STALE: 'STALE',
  CLOSED: 'CLOSED',
  MISSING: 'NO DATA',
  UNSUPPORTED: 'N/A',
}

export const FRESHNESS_HINTS = {
  LIVE: 'Provider timestamp is inside this feed’s freshness budget',
  STALE: 'Older than the freshness budget — the provider has not moved this price',
  CLOSED: 'Market is closed; the last session close is the current price',
  MISSING: 'Watched, but this provider has not returned a quote yet',
  UNSUPPORTED: 'This provider does not quote this asset class',
}

export const MARKET_COLUMNS = [
  {
    id: 'symbol',
    label: 'Symbol',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    cellClass: 'data-table__cell--key',
  },
  { id: 'provider', label: 'Provider' },
  { id: 'assetClass', label: 'Class' },
  {
    id: 'last',
    label: 'Mark',
    numeric: true,
    headerNote: 'normalized',
  },
  {
    id: 'tickChange',
    label: 'Move',
    sortable: false,
    numeric: true,
    headerNote: 'last tick',
  },
  {
    id: 'todayChange',
    label: 'Move',
    numeric: true,
    headerNote: 'today',
  },
  {
    id: 'feed',
    label: 'Feed',
  },
  {
    id: 'age',
    label: 'Age',
    numeric: true,
    headerNote: 'provider',
  },
  {
    id: 'updated',
    label: 'Received',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
  },
  {
    id: 'watch',
    label: '',
    sortable: false,
    headerClass: 'market-cell--watch',
    cellClass: 'market-cell--watch',
  },
]

const MARKET_COLUMNS_HIDDEN_BY_DEFAULT = ['assetClass', 'updated']

export const DEFAULT_MARKET_COLUMNS = MARKET_COLUMNS.filter(
  (column) => !MARKET_COLUMNS_HIDDEN_BY_DEFAULT.includes(column.id),
).map((column) => column.id)

export const DEFAULT_MARKET_SORT = { column: 'symbol', direction: 'asc' }

export const MARKET_FALLBACK_SORT = { column: 'symbol', direction: 'asc' }
