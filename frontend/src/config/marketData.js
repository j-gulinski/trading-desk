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
  { id: 'provider', label: 'Provider', sortable: true, defaultDirection: 'asc' },
  { id: 'assetClass', label: 'Class', sortable: true, defaultDirection: 'asc' },
  {
    id: 'last',
    label: 'Last',
    sortable: true,
    requiresClass: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
  },
  {
    id: 'todayChange',
    label: 'Change',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'today',
  },
  {
    id: 'feed',
    label: 'Market',
    sortable: true,
    snapshot: true,
    defaultDirection: 'asc',
  },
  {
    id: 'age',
    label: 'Quote age',
    sortable: true,
    snapshot: true,
    defaultDirection: 'asc',
    numeric: true,
  },
  {
    id: 'updated',
    label: 'Received',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
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

export const SORT_REQUIRES_CLASS_HINT =
  'Choose one asset class before sorting this column'
