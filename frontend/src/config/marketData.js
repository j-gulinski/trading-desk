export const STREAM_EVENTS = ['market_tick', 'curve_tick']

export const MARKET_STALE_AFTER_MS = 5000

export const HISTORY_LENGTH = 100

export const BOND_CURVE_TENORS = [1, 2, 3, 5, 10]

const CHANGE_COLUMNS = [
  {
    id: 'observedChange',
    label: 'This session',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'Δ vs start',
  },
  {
    id: 'lastTickChange',
    label: 'Last tick Δ',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'vs prior',
  },
]

const TRAILING_COLUMNS = [
  {
    id: 'trend',
    label: 'Trend',
    sortable: false,
    headerNote: `last ${HISTORY_LENGTH}`,
    headerClass: 'market-cell--spark',
    cellClass: 'market-cell--spark',
  },
  {
    id: 'feed',
    label: 'Feed',
    sortable: true,
    snapshot: true,
    defaultDirection: 'asc',
  },
  {
    id: 'updated',
    label: 'Updated',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
  },
]

export const MARKET_COLUMNS = [
  {
    id: 'symbol',
    label: 'Symbol',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    cellClass: 'data-table__cell--key',
  },
  { id: 'assetClass', label: 'Class', sortable: true, defaultDirection: 'asc' },
  {
    id: 'marketLevel',
    label: 'Market level',
    required: true,
    sortable: true,
    requiresClass: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
  },
  ...CHANGE_COLUMNS,
  {
    id: 'quote',
    label: 'Bid / Ask',
    sortable: true,
    requiresClass: true,
    snapshot: true,
    defaultDirection: 'asc',
    numeric: true,
    cellClass: 'market-cell--quote',
  },
  ...TRAILING_COLUMNS,
]

export const CURVE_COLUMNS = [
  {
    id: 'tenor',
    label: 'Tenor',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    cellClass: 'data-table__cell--key',
  },
  {
    id: 'marketLevel',
    label: 'Yield',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
  },
  ...CHANGE_COLUMNS,
  ...TRAILING_COLUMNS,
]

export const DEFAULT_MARKET_SORT = { column: 'assetClass', direction: 'asc' }

export const MARKET_FALLBACK_SORT = { column: 'symbol', direction: 'asc' }

export const DEFAULT_CURVE_SORT = { column: 'tenor', direction: 'asc' }

export const SORT_REQUIRES_CLASS_HINT =
  'Choose one asset class before sorting this column'
